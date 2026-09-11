"""Offline caption & frame embedding ingestion pipeline.

Processes pre-generated VLM captions and frame indices from JSONL, computes SigLIP
visual embeddings for frames and BGE-M3 text embeddings for captions, uploads raw
videos and extracted frames to MinIO, and indexes named vectors into Qdrant.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

from loguru import logger
from minio import Minio
from PIL import Image
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Ensure app is in path when imported
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from ml.encoder import get_encoder, get_qwen_encoder  # noqa: E402


def get_minio_s3_client(
    endpoint: str = "localhost:9003",
    access_key: str = "minioadmin",
    secret_key: str = "minioadmin",
    secure: bool = False,
) -> Minio:
    """Return a working MinIO S3 API client.

    Reads endpoint configuration passed dynamically via argparse or kwargs.
    If the specified port turns out to be the MinIO Web Console port, automatically
    fallback to the S3 API port (e.g. 9003 -> 9002).
    """
    clean_endpoint = endpoint.replace("http://", "").replace("https://", "").rstrip("/")
    client = Minio(clean_endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    try:
        client.list_buckets()
        return client
    except Exception as exc:
        if "API port" in str(exc) and ":" in clean_endpoint:
            host, port_str = clean_endpoint.rsplit(":", 1)
            if port_str.isdigit():
                alt_port = int(port_str) - 1
                alt_endpoint = f"{host}:{alt_port}"
                logger.info(
                    "Endpoint {} returned MinIO Console notice; trying S3 API port {}",
                    clean_endpoint,
                    alt_endpoint,
                )
                client = Minio(
                    alt_endpoint,
                    access_key=access_key,
                    secret_key=secret_key,
                    secure=secure,
                )
                client.list_buckets()
                return client
        raise


class OfflineEmbedderPipeline:
    """Offline embedding pipeline using Qwen (multimodal/caption) and SigLIP (visual)."""

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6335",
        qdrant_api_key: str | None = None,
        minio_endpoint: str = "localhost:9003",
        minio_access_key: str = "minioadmin",
        minio_secret_key: str = "minioadmin",
        collection_name: str = "Scences",
        raw_bucket: str = "scenesearch-raw",
        derived_bucket: str = "scenesearch-derived",
        batch_size: int = 64,
        qwen_model_name: str = "Qwen/Qwen3-VL-Embedding-2B",
    ) -> None:
        self.qdrant_url = qdrant_url
        self.qdrant_api_key = qdrant_api_key
        self.minio_endpoint = minio_endpoint
        self.minio_access_key = minio_access_key
        self.minio_secret_key = minio_secret_key
        self.collection_name = collection_name
        self.raw_bucket = raw_bucket
        self.derived_bucket = derived_bucket
        self.batch_size = batch_size
        self.qwen_model_name = qwen_model_name

        self._siglip: Any = None
        self._qwen_encoder: Any = None
        self._minio_client: Minio | None = None
        self._qdrant_client: QdrantClient | None = None

    def init_clients_and_models(self) -> None:
        """Initialize models and connections eagerly using configured settings."""
        if self._siglip is None:
            logger.info("Loading SigLIP visual encoder...")
            self._siglip = get_encoder()
            if hasattr(self._siglip, "load"):
                self._siglip.load()

        if self._qwen_encoder is None:
            logger.info("Loading Qwen encoder ({model})...", model=self.qwen_model_name)
            self._qwen_encoder = get_qwen_encoder()
            if hasattr(self._qwen_encoder, "load"):
                self._qwen_encoder.load()

        if self._minio_client is None:
            logger.info("Connecting to MinIO S3 storage at {}...", self.minio_endpoint)
            self._minio_client = get_minio_s3_client(
                endpoint=self.minio_endpoint,
                access_key=self.minio_access_key,
                secret_key=self.minio_secret_key,
            )
            # Ensure buckets exist
            for bucket in (self.raw_bucket, self.derived_bucket):
                if not self._minio_client.bucket_exists(bucket):
                    self._minio_client.make_bucket(bucket)
                    logger.info("Created MinIO bucket: {}", bucket)

        if self._qdrant_client is None:
            logger.info("Connecting to Qdrant at {}...", self.qdrant_url)
            self._qdrant_client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key)
            self._ensure_qdrant_collection()

    def _ensure_qdrant_collection(self) -> None:
        assert self._qdrant_client is not None
        if not self._qdrant_client.collection_exists(self.collection_name):
            self._qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "qwen": models.VectorParams(size=2048, distance=models.Distance.COSINE),
                    "siglip": models.VectorParams(size=768, distance=models.Distance.COSINE),
                },
            )
            logger.info(
                "Created Qdrant collection '{}' with named vectors 'qwen' (2048) and 'siglip' (768)",
                self.collection_name,
            )

        # Ensure payload schema indexes
        payload_indexes = {
            "video_id": models.PayloadSchemaType.KEYWORD,
            "frame_idx": models.PayloadSchemaType.INTEGER,
            "frame_no": models.PayloadSchemaType.INTEGER,
            "timestamp_sec": models.PayloadSchemaType.FLOAT,
            "caption_model": models.PayloadSchemaType.KEYWORD,
            "granularity": models.PayloadSchemaType.KEYWORD,
        }
        for field_name, field_schema in payload_indexes.items():
            try:
                self._qdrant_client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
                )
            except Exception as exc:
                if "already exists" not in str(exc).lower():
                    logger.warning("Payload index creation note for {}: {}", field_name, exc)

    def upload_minio_assets(
        self,
        record: dict[str, Any],
        uploaded_videos: set[str],
        uploaded_frames: set[str],
    ) -> tuple[str | None, str | None]:
        """Upload raw video and frame image to MinIO if not already uploaded."""
        assert self._minio_client is not None
        video_id = record["video_id"]
        video_path_str = record.get("video_path")
        frame_path_str = record.get("frame_path")

        raw_key: str | None = None
        frame_key: str | None = None

        # 1. Upload Video
        if video_path_str and Path(video_path_str).is_file():
            ext = Path(video_path_str).suffix.lower() or ".mov"
            raw_key = f"{video_id}{ext}"
            if video_id not in uploaded_videos:
                try:
                    video_type = (
                        "video/mp4" if ext in (".mp4", ".mov") else "application/octet-stream"
                    )
                    self._minio_client.fput_object(
                        self.raw_bucket,
                        raw_key,
                        video_path_str,
                        content_type=video_type,
                    )
                    uploaded_videos.add(video_id)
                except Exception as exc:
                    logger.warning("Failed to upload video {} to MinIO: {}", video_id, exc)

        # 2. Upload Frame
        if frame_path_str and Path(frame_path_str).is_file():
            frame_idx = record.get("frame_idx", record.get("frame_no", 0))
            frame_key = f"{video_id}/frame_{frame_idx:05d}.jpg"
            if frame_key not in uploaded_frames:
                try:
                    self._minio_client.fput_object(
                        self.derived_bucket,
                        frame_key,
                        frame_path_str,
                        content_type="image/jpeg",
                    )
                    uploaded_frames.add(frame_key)
                except Exception as exc:
                    logger.warning("Failed to upload frame {} to MinIO: {}", frame_key, exc)

        return raw_key, frame_key

    def process_jsonl_file(
        self,
        jsonl_path: str | Path,
        limit: int | None = None,
        skip_minio: bool = False,
    ) -> int:
        """Process JSONL dataset line by line, embed, and index into Qdrant & MinIO."""
        self.init_clients_and_models()
        assert self._siglip is not None
        assert self._bge_model is not None
        assert self._qdrant_client is not None

        path = Path(jsonl_path)
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {path}")

        logger.info("Reading caption records from {}", path)
        records: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for line_idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                records.append(json.loads(line))
                if limit and len(records) >= limit:
                    break

        total_records = len(records)
        logger.info("Total records to process: {}", total_records)

        uploaded_videos: set[str] = set()
        uploaded_frames: set[str] = set()
        total_indexed = 0

        for start_idx in range(0, total_records, self.batch_size):
            batch_records = records[start_idx : start_idx + self.batch_size]

            # 1. Load images and prepare captions
            valid_batch: list[dict[str, Any]] = []
            images: list[Image.Image] = []
            captions: list[str] = []

            for r in batch_records:
                fpath = r.get("frame_path")
                caption = r.get("qwen_caption", "").strip() or "Scene frame description"
                if fpath and Path(fpath).is_file():
                    try:
                        img = Image.open(fpath).convert("RGB")
                        images.append(img)
                        captions.append(caption)
                        valid_batch.append(r)
                    except Exception as exc:
                        logger.warning("Could not open image {}: {}", fpath, exc)

            if not valid_batch:
                continue

            # 2. Compute SigLIP Visual Embeddings (768d)
            siglip_vectors = self._siglip.encode_images(images)

            # 3. Compute Qwen Multimodal/Text Embeddings (2048d)
            qwen_vectors = self._qwen_encoder.encode_texts(captions)

            # 4. Upload to MinIO & Build Qdrant Points
            points: list[models.PointStruct] = []
            for r, sig_vec, qwen_vec in zip(valid_batch, siglip_vectors, qwen_vectors):
                raw_key, frame_key = (None, None)
                if not skip_minio:
                    raw_key, frame_key = self.upload_minio_assets(
                        r, uploaded_videos, uploaded_frames
                    )

                v_id = r["video_id"]
                f_idx = r.get("frame_idx", r.get("frame_no", 0))

                # Deterministic point ID based on video_id and frame_idx
                point_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{v_id}_frame_{f_idx}"))

                caption_text = r.get("qwen_caption") or r.get("caption") or ""
                present_concepts: list[str] = []
                absent_concepts: list[str] = []
                if caption_text:
                    from search.query import concept_names, resolve_concept, split_clauses

                    clauses = split_clauses(caption_text)
                    for concept in concept_names():
                        pol, _ = resolve_concept(clauses, concept)
                        if pol == "present":
                            present_concepts.append(concept)
                        elif pol == "absent":
                            absent_concepts.append(concept)

                payload = {
                    "video_id": v_id,
                    "video_path": r.get("video_path"),
                    "frame_path": r.get("frame_path"),
                    "frame_no": r.get("frame_no"),
                    "frame_idx": f_idx,
                    "timestamp_sec": r.get("timestamp_sec"),
                    "dedup_group_size": r.get("dedup_group_size", 1),
                    "dedup_span_sec": r.get("dedup_span_sec", []),
                    "qwen_caption": r.get("qwen_caption"),
                    "caption_model": r.get("caption_model", "qwen3-vl:2b-instruct"),
                    "raw_minio_key": raw_key,
                    "frame_minio_key": frame_key,
                    "granularity": "frame",
                    "model_version": "qwen3-vl-embedding-2b-v1",
                    "present_concepts": present_concepts,
                    "absent_concepts": absent_concepts,
                }

                points.append(
                    models.PointStruct(
                        id=point_uuid,
                        vector={
                            "siglip": sig_vec,
                            "qwen": qwen_vec,
                        },
                        payload=payload,
                    )
                )

                # Close PIL images to save memory
                for img in images:
                    img.close()

            # 5. Upsert batch into Qdrant
            if points:
                self._qdrant_client.upsert(
                    collection_name=self.collection_name,
                    points=points,
                    wait=True,
                )
                total_indexed += len(points)
                logger.info(
                    "Processed [{}/{}]: Upserted {} points to Qdrant",
                    min(start_idx + self.batch_size, total_records),
                    total_records,
                    len(points),
                )

        logger.success("Offline ingestion completed! Total points indexed: {}", total_indexed)
        return total_indexed


__all__ = ["OfflineEmbedderPipeline", "get_minio_s3_client"]

"""Complete video ingestion Celery task: 2FPS sampling, SigLIP >0.95 similarity deduplication, Qwen3-VL captioning, BGE-M3 text embedding, and Qdrant named-vector indexing."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List
import uuid

from celery import Task
from loguru import logger
from qdrant_client.http import models

from infrastructure.qdrant import get_qdrant_client, init_qdrant_collections
from repositories.task_status import TaskStatusStoreError, update_task_status
from schemas.task import TaskStatus
from worker.celery_app import celery_app
from worker.task_names import INGESTION_TASK_NAME

from ml.embedder import SigLIPVisualEmbedder, BGEM3TextEmbedder
from ml.captioner import QwenVLCaptioner
from worker.pipelines.video import extract_and_deduplicate_frames


async def _report_progress(
    task: Task,
    task_id: str,
    *,
    progress: int,
    stage: str,
) -> None:
    await update_task_status(task_id, TaskStatus.PROCESSING, progress=progress)
    task.update_state(state="PROGRESS", meta={"progress": progress, "stage": stage})


async def _run_ingestion(task: Task, task_id: str, video_path: str) -> dict[str, Any]:
    logger.info(
        "Starting video ingestion task {task_id} for {video_path}",
        task_id=task_id,
        video_path=video_path,
    )
    try:
        await _report_progress(task, task_id, progress=5, stage="starting")

        # 1. Initialize Qdrant Collection
        qdrant = get_qdrant_client()
        await init_qdrant_collections(qdrant)
        await _report_progress(task, task_id, progress=10, stage="qdrant_ready")

        video_name = Path(video_path).stem
        count_res = await qdrant.count(
            collection_name="scenes",
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="video_id",
                        match=models.MatchValue(value=video_name)
                    )
                ]
            )
        )
        if count_res.count > 0:
            logger.info("Video '{video_name}' has already been ingested ({count} points in Qdrant). Skipping!", video_name=video_name, count=count_res.count)
            result = {"video_path": video_path, "frames_indexed": count_res.count, "skipped": True}
            await update_task_status(task_id, TaskStatus.COMPLETED, progress=100, result=result)
            return result

        # 2. Load ML Models
        siglip_embedder = SigLIPVisualEmbedder()
        qwen_captioner = QwenVLCaptioner()
        bge_embedder = BGEM3TextEmbedder()
        await _report_progress(task, task_id, progress=20, stage="models_loaded")

        # 3. Step 1: 2FPS Frame Decoding + SigLIP Embedding + Similarity Deduplication (>0.95 dropped)
        retained_frames = extract_and_deduplicate_frames(
            video_path,
            embedder=siglip_embedder,
            target_fps=2.0,
            sim_threshold=0.95
        )
        await _report_progress(task, task_id, progress=50, stage="frames_deduplicated")

        if not retained_frames:
            logger.warning("No valid frames retained after deduplication for task {task_id}", task_id=task_id)
            result = {"video_path": video_path, "frames_indexed": 0}
            await update_task_status(task_id, TaskStatus.COMPLETED, progress=100, result=result)
            return result

        # 4. Step 2: Qwen3-VL Captioning + BGE-M3 Text Embedding
        logger.info(f"Generating Qwen3-VL captions for {len(retained_frames)} deduplicated frames...")
        captions: List[str] = []
        for i, frec in enumerate(retained_frames):
            caption = qwen_captioner.generate_caption(frec["image"])
            if not caption:
                caption = f"Keyframe scene at timestamp {frec['timestamp_sec']}s"
            captions.append(caption)
            frec["qwen_caption"] = caption

            if (i + 1) % 5 == 0 or (i + 1) == len(retained_frames):
                pct = 50 + int(((i + 1) / len(retained_frames)) * 30)
                await _report_progress(task, task_id, progress=pct, stage="captions_generated")

        # BGE-M3 Text Encoding
        logger.info(f"Encoding {len(captions)} text captions with BGE-M3...")
        text_vectors = bge_embedder.encode_texts(captions)
        await _report_progress(task, task_id, progress=85, stage="text_embeddings_generated")

        # Upload Assets to MinIO
        minio_video_key = None
        minio_thumbnail_keys = {}
        try:
            from infrastructure.minio import MinIOStorage
            storage = MinIOStorage()
            storage.ensure_bucket()

            # Upload Video
            v_path = Path(video_path)
            v_ext = v_path.suffix.lower() or ".mp4"
            v_obj_name = f"videos/{video_name}{v_ext}"
            storage.upload_file(v_obj_name, v_path, content_type="video/mp4")
            minio_video_key = v_obj_name

            # Upload Thumbnails
            tmp_dir = Path("/tmp/scenesearch_thumbs") / video_name
            tmp_dir.mkdir(parents=True, exist_ok=True)

            for frec in retained_frames:
                f_no = frec["frame_no"]
                thumb_path = tmp_dir / f"f{f_no}.jpg"
                frec["image"].save(thumb_path, format="JPEG", quality=85)
                t_obj_name = f"thumbnails/{video_name}/f{f_no}.jpg"
                storage.upload_file(t_obj_name, thumb_path, content_type="image/jpeg")
                minio_thumbnail_keys[f_no] = t_obj_name

            logger.info("Uploaded video and {count} frame thumbnails to MinIO S3", count=len(minio_thumbnail_keys))
        except Exception as exc:
            logger.warning("MinIO upload skipped ({exc})", exc=exc)

        # 5. Step 3: Build Qdrant Named Vector Points & Upsert
        points = []
        for i, (frec, t_vec) in enumerate(zip(retained_frames, text_vectors)):
            raw_id_str = f"{video_name}_f{frec['frame_no']}_{i}"
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, raw_id_str))

            f_no = frec["frame_no"]
            payload = {
                "video_id": video_name,
                "video_path": video_path,
                "timestamp_sec": frec["timestamp_sec"],
                "frame_no": f_no,
                "frame_idx": frec["frame_idx"],
                "qwen_caption": frec["qwen_caption"],
            }
            if minio_video_key:
                payload["minio_video_key"] = minio_video_key
            if f_no in minio_thumbnail_keys:
                payload["minio_thumbnail_key"] = minio_thumbnail_keys[f_no]

            points.append(
                models.PointStruct(
                    id=point_id,
                    vector={
                        "siglip_visual": frec["siglip_vector"].tolist(),
                        "bge_text": t_vec.tolist(),
                    },
                    payload=payload,
                )
            )

        await qdrant.upsert(collection_name="scenes", points=points)
        await _report_progress(task, task_id, progress=95, stage="qdrant_upserted")

        result: dict[str, Any] = {
            "video_path": video_path,
            "retained_frames": len(retained_frames),
            "siglip_dimensions": 768,
            "bge_dimensions": 1024,
            "dedup_threshold": 0.95,
            "qdrant_collection": "scenes",
        }
        await update_task_status(
            task_id,
            TaskStatus.COMPLETED,
            progress=100,
            result=result,
        )
        logger.info("Completed video ingestion task {task_id}", task_id=task_id)
        return result

    except Exception as exc:
        logger.exception("Video ingestion task {task_id} failed", task_id=task_id)
        failure_status = (
            TaskStatus.RETRYING
            if isinstance(exc, (ConnectionError, TaskStatusStoreError))
            else TaskStatus.FAILED
        )
        try:
            await update_task_status(
                task_id,
                failure_status,
                progress=0,
                error=str(exc),
            )
        except Exception:
            logger.exception("Could not persist failure state for task {task_id}", task_id=task_id)
        raise


@celery_app.task(
    bind=True,
    name=INGESTION_TASK_NAME,
    max_retries=3,
    default_retry_delay=10,
)
def ingest_video(self: Task, task_id: str, video_path: str) -> dict[str, Any]:
    """Celery entrypoint wrapping the async ingestion workflow."""
    return asyncio.run(_run_ingestion(self, task_id, video_path))


process_video_ingestion = ingest_video


def _mock_embedding_digest(task_id: str, video_path: str, frame_count: int) -> str:
    import hashlib
    raw = f"{task_id}:{video_path}:{frame_count}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()



"""Owned chunk/keyframe collections and compensated multi-collection writes."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger
from qdrant_client import models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from core.config import QdrantSettings, get_settings
from core.privacy import is_anonymized_playback, is_anonymized_thumbnail
from infrastructure.qdrant import get_qdrant_client
from ml.vectors import normalize_vectors
from pipelines.common.errors import PersistenceError, RetryablePersistenceError

CHUNK_VECTORS = {"siglip", "qwen", "caption"}
KEYFRAME_VECTORS = {"siglip"}


@dataclass(frozen=True)
class RepresentationPoints:
    chunks: tuple[Any, ...]
    keyframes: tuple[Any, ...]
    run_id: str
    fingerprint: str
    dimensions: dict[str, int]


class SceneVectorIndexer:
    def __init__(self, settings: QdrantSettings | None = None, *, client: Any = None) -> None:
        self.settings = settings or get_settings().qdrant
        self.client = client
        self._dimensions: dict[str, int] = {}

    def _client(self):
        return self.client if self.client is not None else get_qdrant_client()

    def _collections(self):
        return (
            (
                self.settings.chunk_collection,
                {key: self._dimensions.get(key) for key in CHUNK_VECTORS},
            ),
            (
                self.settings.keyframe_collection,
                {key: self._dimensions.get(key) for key in KEYFRAME_VECTORS},
            ),
        )

    async def preflight_models(self, dimensions: dict[str, int]) -> None:
        if set(dimensions) != CHUNK_VECTORS or any(size <= 0 for size in dimensions.values()):
            raise ValueError("Invalid encoder dimension contract")
        self._dimensions = dict(dimensions)
        await self._preflight_collections(create=False)

    async def _preflight_collections(self, *, create: bool) -> None:
        try:
            for name, expected in self._collections():
                await self._ensure_collection(name, expected, create=create)
        except UnexpectedResponse as exc:
            if exc.status_code == 429 or (exc.status_code or 0) >= 500:
                raise RetryablePersistenceError(
                    "Vector preflight is temporarily unavailable", stage="preflight"
                ) from exc
            raise PersistenceError("Vector preflight was rejected", stage="preflight") from exc
        except (
            ResponseHandlingException,
            httpx.TransportError,
            ConnectionError,
            TimeoutError,
        ) as exc:
            raise RetryablePersistenceError(
                "Unable to reach the vector index", stage="preflight"
            ) from exc

    async def _ensure_collection(self, name, expected, *, create: bool):
        client = self._client()
        if not await client.collection_exists(name):
            if not create:
                return False
            try:
                await client.create_collection(
                    collection_name=name,
                    vectors_config={
                        key: models.VectorParams(size=size, distance=models.Distance.COSINE)
                        for key, size in expected.items()
                    },
                    quantization_config=models.ScalarQuantization(
                        scalar=models.ScalarQuantizationConfig(
                            type=models.ScalarType.INT8,
                            quantile=0.99,
                            always_ram=False,
                        )
                    ),
                )
            except UnexpectedResponse as exc:
                if exc.status_code != 409:
                    raise
                # Another worker won creation; validate its schema below.
        info = await client.get_collection(name)
        vectors = info.config.params.vectors
        if (
            not isinstance(vectors, dict)
            or set(vectors) != set(expected)
            or any(
                (size is not None and vectors[key].size != size)
                or vectors[key].size <= 0
                or vectors[key].distance != models.Distance.COSINE
                for key, size in expected.items()
            )
        ):
            raise ValueError(f"Incompatible collection schema: {name}")
        if create:
            fields = {
                key: models.PayloadSchemaType.KEYWORD
                for key in (
                    "video_id",
                    "semantic_scene_id",
                    "chunk_id",
                    "chunk_ids",
                    "keyframe_ids",
                    "ingestion_fingerprint",
                    "ingestion_run_id",
                    "model_version",
                    "siglip_embedding_version",
                    "qwen_embedding_version",
                    "caption_embedding_version",
                    "privacy_status",
                    "objects",
                    "present_concepts",
                    "absent_concepts",
                    "dataset",
                )
            }
            fields.update(
                {
                    "ts_start_s": models.PayloadSchemaType.FLOAT,
                    "ts_end_s": models.PayloadSchemaType.FLOAT,
                }
            )
            for key, kind in fields.items():
                await client.create_payload_index(
                    collection_name=name, field_name=key, field_schema=kind, wait=True
                )
        return True

    async def preflight(self, batch: RepresentationPoints) -> None:
        if set(batch.dimensions) != CHUNK_VECTORS or any(
            not isinstance(size, int) or size <= 0 for size in batch.dimensions.values()
        ):
            raise ValueError("Invalid encoder dimension contract")
        self._dimensions = dict(batch.dimensions)
        seen = set()
        for points, expected, required in (
            (
                batch.chunks,
                {key: batch.dimensions[key] for key in CHUNK_VECTORS},
                {"siglip", "qwen"},
            ),
            (batch.keyframes, {"siglip": batch.dimensions["siglip"]}, {"siglip"}),
        ):
            if not points:
                raise ValueError("representation requires chunk and keyframe points")
            for point in points:
                if point.id in seen:
                    raise ValueError("Duplicate representation point ID")
                seen.add(point.id)
                if not isinstance(point.vector, dict) or not required <= set(point.vector) <= set(
                    expected
                ):
                    raise ValueError("Invalid vector names")
                for key, vector in point.vector.items():
                    normalize_vectors([vector], dimension=expected[key])
                if (
                    point.payload.get("ingestion_fingerprint") != batch.fingerprint
                    or point.payload.get("ingestion_run_id") != batch.run_id
                    or point.payload.get("privacy_status") != "verified"
                ):
                    raise ValueError("Mixed or unverified representation publication")
                if not is_anonymized_thumbnail(
                    point.payload.get("thumbnail_key")
                ) or not is_anonymized_playback(point.payload.get("video_key")):
                    raise ValueError("Representation points require verified derivative media")
        chunks = {str(point.id): point.payload for point in batch.chunks}
        frames = {str(point.id): point.payload for point in batch.keyframes}
        if len({point.payload.get("video_id") for point in (*batch.chunks, *batch.keyframes)}) != 1:
            raise ValueError("Representation spans multiple source videos")
        for point in batch.chunks:
            data = point.payload
            if data.get("chunk_id") != str(point.id) or data.get("granularity") != "segment":
                raise ValueError("Chunk point identity does not match its payload")
            if (data.get("caption_embedding_status") == "ready") != (
                "caption" in point.vector
            ) or data.get("caption_embedding_status") not in ("ready", "not_available"):
                raise ValueError("Caption embedding status does not match its vector")
            ids = data.get("keyframe_ids") or []
            if not ids or len(set(ids)) != len(ids) or any(key not in frames for key in ids):
                raise ValueError("Chunk references missing or duplicate keyframes")
            start, end = data.get("start_ms"), data.get("end_ms")
            if (
                start is None
                or end is None
                or not all(math.isfinite(value) for value in (start, end))
                or not 0 <= start < end
            ):
                raise ValueError("Invalid chunk point timestamps")
        for identifier, data in frames.items():
            if data.get("keyframe_id") != identifier or data.get("granularity") != "frame":
                raise ValueError("Keyframe point identity does not match its payload")
            ids = data.get("chunk_ids") or []
            if not ids or len(set(ids)) != len(ids) or any(key not in chunks for key in ids):
                raise ValueError("Keyframe references missing or duplicate chunks")
            for chunk_id in ids:
                chunk = chunks[chunk_id]
                if (
                    identifier not in chunk["keyframe_ids"]
                    or data.get("semantic_scene_id") != chunk.get("semantic_scene_id")
                    or not chunk["start_ms"] <= data.get("timestamp_ms", -1) < chunk["end_ms"]
                ):
                    raise ValueError("Keyframe/chunk relationships are inconsistent")
        for chunk_id, data in chunks.items():
            if any(chunk_id not in frames[key]["chunk_ids"] for key in data["keyframe_ids"]):
                raise ValueError("Chunk/keyframe relationships are not bidirectional")
        await self._preflight_collections(create=True)

    async def delete_by_video(self, video_id: str, *, run_id: str | None = None) -> None:
        if not video_id:
            raise ValueError("video_id must not be empty")
        conditions = [
            models.FieldCondition(key="video_id", match=models.MatchValue(value=video_id))
        ]
        if run_id is not None:
            conditions.append(
                models.FieldCondition(key="ingestion_run_id", match=models.MatchValue(value=run_id))
            )

        async def remove(name, expected):
            if await self._ensure_collection(name, expected, create=False):
                await self._client().delete(
                    collection_name=name,
                    points_selector=models.FilterSelector(
                        filter=models.Filter(
                            must=conditions,
                        )
                    ),
                    wait=True,
                )

        results = await asyncio.gather(
            *(remove(name, schema) for name, schema in self._collections()), return_exceptions=True
        )
        for result in results:
            if isinstance(result, BaseException):
                raise RuntimeError("Unable to clean all vector collections") from result

    async def reindex_video(self, video_id: str, batch: RepresentationPoints) -> int:
        if any(
            point.payload.get("video_id") != video_id for point in (*batch.chunks, *batch.keyframes)
        ):
            raise ValueError("Representation point belongs to another video")
        await self.preflight(batch)
        await self.delete_by_video(video_id, run_id=batch.run_id)
        written = 0
        try:
            for name, points in (
                (self.settings.chunk_collection, batch.chunks),
                (self.settings.keyframe_collection, batch.keyframes),
            ):
                for start in range(0, len(points), 256):
                    items = list(points[start : start + 256])
                    await self._client().upsert(collection_name=name, points=items, wait=True)
                    written += len(items)
            return written
        except (Exception, asyncio.CancelledError):
            try:
                await self.delete_by_video(video_id, run_id=batch.run_id)
            except Exception:
                logger.exception("Failed to remove partial representation for {}", video_id)
            raise


async def delete_scene_vectors(video_id: str) -> None:
    await SceneVectorIndexer().delete_by_video(video_id)

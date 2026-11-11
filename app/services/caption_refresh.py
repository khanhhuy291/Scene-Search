"""Refresh fallback scene captions from stored derived thumbnails."""

from __future__ import annotations

import io
import re
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger
from PIL import Image
from qdrant_client import AsyncQdrantClient, models

from core.config import get_settings
from infrastructure.minio import get_derived_storage
from infrastructure.qdrant import get_qdrant_client
from pipelines.common.types import FrameRecord, SceneRecord
from pipelines.ingestion.metadata_extractor import extract_scene_vlm_metadata
from infrastructure.redis import get_redis_client

_FALLBACK_CAPTION = re.compile(r"^Dashcam driving scene at\s+\d+(?:\.\d+)?s\.$")
_CATALOG_GENERATION_KEY = "scenesearch:search-catalog-generation"
_PAGE_SIZE = 500
_BATCH_SIZE = 8

ProgressCallback = Callable[[int], Awaitable[None]]


def _caption(payload: dict[str, Any]) -> str:
    metadata = payload.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return str(payload.get("caption") or metadata.get("caption") or "").strip()


def _is_fallback(payload: dict[str, Any]) -> bool:
    caption = _caption(payload)
    return not caption or bool(_FALLBACK_CAPTION.fullmatch(caption))


def _image_from_storage(object_key: str) -> Image.Image:
    raw = get_derived_storage().read_object(object_key)
    with Image.open(io.BytesIO(raw)) as image:
        return image.convert("RGB")


async def _collect_candidates(
    client: AsyncQdrantClient,
    video_ids: set[str] | None,
) -> list[tuple[str | int, dict[str, Any]]]:
    settings = get_settings().qdrant
    candidates: list[tuple[str | int, dict[str, Any]]] = []
    offset: Any = None
    while True:
        points, offset = await client.scroll(
            collection_name=settings.collection,
            limit=_PAGE_SIZE,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            if video_ids is not None and str(payload.get("video_id") or "") not in video_ids:
                continue
            if _is_fallback(payload):
                candidates.append((point.id, payload))
        if offset is None:
            break
    return candidates


def _make_scene(point_id: str | int, payload: dict[str, Any]) -> SceneRecord:
    thumbnail_key = (
        payload.get("thumbnail_key")
        or payload.get("minio_path")
        or payload.get("minio_thumbnail_key")
        or payload.get("frame_minio_key")
    )
    if not isinstance(thumbnail_key, str) or not thumbnail_key.strip():
        raise ValueError(f"Qdrant point {point_id} has no thumbnail object key")

    video_id = str(payload.get("video_id") or "")
    if not video_id:
        raise ValueError(f"Qdrant point {point_id} has no video_id")

    start_ms = int(payload.get("start_ms") or round(float(payload.get("ts_start_s") or 0) * 1000))
    end_ms = int(payload.get("end_ms") or round(float(payload.get("ts_end_s") or 0) * 1000))
    frame_index = int(payload.get("frame_id") or 0)
    image = _image_from_storage(thumbnail_key)
    frame = FrameRecord(
        timestamp_ms=start_ms,
        frame_index=frame_index,
        image=image,
        privacy_status="verified",
    )
    return SceneRecord(
        scene_id=str(payload.get("scene_id") or payload.get("segment_id") or point_id),
        video_id=video_id,
        start_ms=start_ms,
        end_ms=max(start_ms, end_ms),
        keyframes=[frame],
        thumbnail_key=thumbnail_key,
    )


async def refresh_fallback_captions(
    *,
    video_ids: set[str] | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Refresh only missing/template captions; leave descriptive VLM payloads intact."""

    settings = get_settings()
    if not settings.llm.api_key or not settings.llm.api_key.get_secret_value():
        raise RuntimeError("LLM_API_KEY is required to refresh captions")

    qdrant = get_qdrant_client()
    candidates = await _collect_candidates(qdrant, video_ids)
    total = len(candidates)
    if total == 0:
        return {"selected": 0, "updated": 0, "failed": 0, "skipped": 0}

    updated = failed = 0
    failures: list[dict[str, str]] = []
    for batch_start in range(0, total, _BATCH_SIZE):
        batch = candidates[batch_start : batch_start + _BATCH_SIZE]
        scenes: list[SceneRecord] = []
        point_ids: list[str | int] = []
        for point_id, payload in batch:
            try:
                scenes.append(_make_scene(point_id, payload))
                point_ids.append(point_id)
            except Exception as exc:
                failed += 1
                failures.append({"point_id": str(point_id), "error": str(exc)[:240]})

        try:
            await extract_scene_vlm_metadata(scenes, max_concurrency=2)
        except Exception as exc:
            logger.exception("Caption refresh batch failed: {error}", error=exc)
            failed += len(scenes)
            failures.extend(
                {"point_id": str(point_id), "error": str(exc)[:240]}
                for point_id in point_ids
            )
            for scene in scenes:
                scene.keyframes[0].image.close()
            scenes = []
            point_ids = []

        for point_id, scene in zip(point_ids, scenes, strict=True):
            frame = scene.keyframes[0]
            vlm_data = frame.metadata.get("vlm_data") or {}
            metadata = vlm_data.get("metadata") or {}
            caption = str(metadata.get("caption") or "").strip()
            if not caption or _FALLBACK_CAPTION.fullmatch(caption):
                failed += 1
                failures.append({"point_id": str(point_id), "error": "VLM returned fallback caption"})
                continue

            tags = metadata.get("retrieval_tags") or []
            payload = {
                "metadata": metadata,
                "caption": caption,
                "retrieval_tags": tags,
                "present_concepts": vlm_data.get("present_concepts") or [],
                "absent_concepts": vlm_data.get("absent_concepts") or [],
            }
            try:
                await qdrant.set_payload(
                    collection_name=settings.qdrant.collection,
                    payload=payload,
                    points=[point_id],
                    wait=True,
                )
                updated += 1
            except Exception as exc:
                failed += 1
                failures.append({"point_id": str(point_id), "error": str(exc)[:240]})
                logger.exception(
                    "Unable to update caption payload for point {point_id}", point_id=point_id
                )

        for scene in scenes:
            scene.keyframes[0].image.close()

        if progress:
            done = min(batch_start + len(batch), total)
            await progress(round(done * 100 / total))

    if updated:
        try:
            await get_redis_client().incr(_CATALOG_GENERATION_KEY)
        except Exception:
            # Search remains correct after the catalog TTL; Redis invalidation
            # only controls how quickly the changed captions become visible.
            logger.exception("Could not signal search catalog reload after caption refresh")

    return {
        "selected": total,
        "updated": updated,
        "failed": failed,
        "skipped": 0,
        "failed_points": failures[:50],
        "catalog_reload_requested": bool(updated),
    }


__all__ = ["refresh_fallback_captions"]

"""Refresh fallback scene captions from stored derived thumbnails."""

from __future__ import annotations

import io
import re
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger
from PIL import Image
from qdrant_client import AsyncQdrantClient

from core.config import get_settings
from core.privacy import is_anonymized_thumbnail
from infrastructure.minio import get_derived_storage
from infrastructure.qdrant import get_qdrant_client
from pipelines.common.types import FrameRecord, SceneRecord
from pipelines.ingestion.metadata_extractor import extract_scene_vlm_metadata
from pipelines.ingestion.scene_metadata import (
    aggregate_observations,
    canonical_concepts,
    metadata_payload,
)
from schemas.scene_evidence import SceneEvidence
from services.catalog_generation import invalidate_catalog

_FALLBACK_CAPTION = re.compile(r"^Dashcam driving scene at\s+\d+(?:\.\d+)?s\.$")
_PAGE_SIZE = 500
_BATCH_SIZE = 8

ProgressCallback = Callable[[int], Awaitable[None]]


def _caption(payload: dict[str, Any]) -> str:
    metadata = payload.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return str(payload.get("caption") or metadata.get("caption") or "").strip()


def _is_fallback(payload: dict[str, Any]) -> bool:
    metadata = payload.get("metadata") or {}
    if metadata.get("schema_version") == 2:
        evidence = SceneEvidence.model_validate(metadata)
        return any(
            o.frame_index == evidence.representative_frame_index and o.status != "success"
            for o in evidence.observations
        )
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
    if not is_anonymized_thumbnail(thumbnail_key):
        raise ValueError(f"Qdrant point {point_id} has no anonymized thumbnail")

    video_id = str(payload.get("video_id") or "")
    if not video_id:
        raise ValueError(f"Qdrant point {point_id} has no video_id")

    start_ms = int(payload.get("start_ms") or round(float(payload.get("ts_start_s") or 0) * 1000))
    end_ms = int(payload.get("end_ms") or round(float(payload.get("ts_end_s") or 0) * 1000))
    frame_index = int(
        payload["representative_frame_index"]
        if payload.get("representative_frame_index") is not None
        else payload.get("frame_id") or 0
    )
    frame_timestamp = (
        int(payload["representative_timestamp_ms"])
        if payload.get("representative_timestamp_ms") is not None
        else start_ms
    )
    image = _image_from_storage(thumbnail_key)
    frame = FrameRecord(
        timestamp_ms=frame_timestamp,
        frame_index=frame_index,
        image=image,
        display_image=image,
        privacy_status="verified",
    )
    return SceneRecord(
        scene_id=str(payload.get("scene_id") or payload.get("segment_id") or point_id),
        video_id=video_id,
        start_ms=start_ms,
        end_ms=max(start_ms, end_ms),
        keyframes=[frame],
        thumbnail_key=thumbnail_key,
        representative_frame=frame,
        vlm_candidates=[frame],
    )


def refresh_payload(original: dict[str, Any], fresh: dict[str, Any]) -> dict[str, Any]:
    """Merge only the thumbnail observation; preserve evidence for other frames."""
    fresh_evidence = SceneEvidence.model_validate(fresh["metadata"])
    metadata = original.get("metadata") or {}
    if metadata.get("schema_version") == 2:
        old = SceneEvidence.model_validate(metadata)
        refreshed = fresh_evidence.observations[0]
        if (
            refreshed.frame_index != old.representative_frame_index
            or refreshed.timestamp_ms != old.representative_timestamp_ms
        ):
            raise ValueError("Refreshed thumbnail does not match the representative reference")
        previous = next(o for o in old.observations if o.frame_index == refreshed.frame_index)
        # Stored detections/behaviors are not recomputed by thumbnail-only VLM.
        refreshed = refreshed.model_copy(
            update={
                "objects": previous.objects,
                "object_counts": previous.object_counts,
                "behaviors": previous.behaviors,
                "present_concepts": sorted(
                    set(refreshed.present_concepts) | canonical_concepts(previous.objects)
                ),
                "absent_concepts": sorted(
                    set(refreshed.absent_concepts) - canonical_concepts(previous.objects)
                ),
            }
        )
        fresh = aggregate_observations(
            [refreshed if o.frame_index == refreshed.frame_index else o for o in old.observations],
            sampled_count=old.sampled_count,
            representative_frame_index=old.representative_frame_index,
            representative_timestamp_ms=old.representative_timestamp_ms,
        )
    else:
        # A legacy segment's counts/behaviors may span the whole scene. Keep
        # v1 rather than inventing per-thumbnail evidence for those fields.
        observation = fresh_evidence.observations[0]
        metadata = {**metadata, **observation.attributes, "caption": observation.caption}
        detected = canonical_concepts(
            list(original.get("objects") or []) + list(original.get("object_counts") or {})
        )
        positive = set(observation.present_concepts) | detected
        fresh = {
            "metadata": metadata,
            "enrichment": fresh.get("enrichment"),
            "present_concepts": sorted(positive),
            "absent_concepts": sorted(set(observation.absent_concepts) - positive),
        }
    fresh["metadata"]["refresh_scope"] = "thumbnail_only"
    return metadata_payload(fresh)


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

        updated_before_batch = updated
        try:
            try:
                await extract_scene_vlm_metadata(scenes, settings=settings)
            except Exception as exc:
                logger.exception("Caption refresh batch failed: {error}", error=exc)
                failed += len(scenes)
                failures.extend(
                    {"point_id": str(point_id), "error": str(exc)[:240]} for point_id in point_ids
                )
            else:
                for point_id, scene in zip(point_ids, scenes, strict=True):
                    try:
                        fresh = scene.metadata["vlm_data"]
                        if fresh["enrichment"]["status"] != "success":
                            raise ValueError("Thumbnail enrichment did not succeed")
                        payload = refresh_payload(dict(batch)[point_id], fresh)
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
                            "Unable to refresh caption for point {point_id}", point_id=point_id
                        )
        finally:
            for scene in scenes:
                scene.keyframes[0].close()
            if updated > updated_before_batch:
                await invalidate_catalog()

        if progress:
            done = min(batch_start + len(batch), total)
            await progress(round(done * 100 / total))

    return {
        "selected": total,
        "updated": updated,
        "failed": failed,
        "skipped": 0,
        "failed_points": failures[:50],
        "catalog_reload_requested": bool(updated),
    }


__all__ = ["refresh_fallback_captions"]

"""Refresh incomplete published chunks from stored timestamped frame sequences."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger
from PIL import Image
from qdrant_client import AsyncQdrantClient, models

from core.config import get_settings
from core.privacy import is_anonymized_thumbnail
from infrastructure.minio import get_derived_storage
from infrastructure.qdrant import get_qdrant_client
from ml.encoder import get_qwen_encoder
from ml.vectors import normalize_vectors
from pipelines.common.types import FrameRecord, SceneRecord
from pipelines.ingestion.metadata_extractor import extract_scene_vlm_metadata
from pipelines.ingestion.scene_metadata import (
    metadata_payload,
)
from repositories.scene_graph import active_publications, lock_active_publication
from schemas.scene_evidence import SceneEvidence
from search.publication import published_chunks
from services.catalog_generation import invalidate_catalog

_BATCH_SIZE = 8

ProgressCallback = Callable[[int], Awaitable[None]]


def _caption(payload: dict[str, Any]) -> str:
    metadata = payload.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return str(payload.get("caption") or metadata.get("caption") or "").strip()


def _is_fallback(payload: dict[str, Any]) -> bool:
    metadata = payload.get("metadata") or {}
    evidence = SceneEvidence.model_validate(metadata)
    return any(o.status != "success" for o in evidence.observations) or not _caption(payload)


def _image_from_storage(object_key: str) -> Image.Image:
    raw = get_derived_storage().read_object(object_key)
    with Image.open(io.BytesIO(raw)) as image:
        return image.convert("RGB")


async def _collect_candidates(
    client: AsyncQdrantClient,
    video_ids: set[str] | None,
) -> list[tuple[str | int, dict[str, Any]]]:
    publications = await active_publications(video_ids)
    points = await published_chunks(client, publications)
    return [(point.id, point.payload) for point in points.values() if _is_fallback(point.payload)]


async def _make_sequence(
    client: AsyncQdrantClient, point_id: str | int, payload: dict[str, Any]
) -> SceneRecord:
    evidence = SceneEvidence.model_validate(payload["metadata"])
    records = await client.retrieve(
        collection_name=get_settings().qdrant.keyframe_collection,
        ids=payload.get("vlm_frame_ids") or payload["keyframe_ids"],
        with_payload=True,
        with_vectors=False,
    )
    by_reference = {
        (point.payload["frame_id"], point.payload["timestamp_ms"]): point.payload
        for point in records
    }
    if evidence.candidate_count > get_settings().video.vlm_max_frames:
        raise ValueError(
            "Stored sequence exceeds the configured VLM frame budget; re-ingest with the selected budget"
        )
    frames = []
    try:
        for observation in evidence.observations:
            data = by_reference.get((observation.frame_index, observation.timestamp_ms))
            if (
                data is None
                or data.get("ingestion_run_id") != payload["ingestion_run_id"]
                or data.get("video_id") != payload["video_id"]
                or str(point_id) not in data.get("chunk_ids", [])
                or not is_anonymized_thumbnail(data.get("thumbnail_key"))
            ):
                raise ValueError("Stored VLM sequence is incomplete; re-ingest this video")
            image = await asyncio.to_thread(_image_from_storage, data["thumbnail_key"])
            frames.append(
                FrameRecord(
                    observation.timestamp_ms,
                    observation.frame_index,
                    image,
                    display_image=image,
                    privacy_status="verified",
                )
            )
        frames.sort(key=lambda frame: (frame.timestamp_ms, frame.frame_index))
        representative = next(
            frame for frame in frames if frame.frame_index == evidence.representative_frame_index
        )
        return SceneRecord(
            str(point_id),
            payload["video_id"],
            payload["start_ms"],
            payload["end_ms"],
            frames,
            representative_frame=representative,
            vlm_candidates=frames,
            metadata={"sampled_frame_count": evidence.sampled_count},
        )
    except BaseException:
        for frame in frames:
            frame.close()
        raise


async def _write_sequence(
    client: AsyncQdrantClient, point_id: str | int, original: dict[str, Any], fresh: dict[str, Any]
) -> None:
    encoder = get_qwen_encoder()
    caption = fresh["metadata"]["caption"]
    vector = normalize_vectors(
        await asyncio.to_thread(encoder.encode_texts, [caption]),
        dimension=encoder.dimension,
        count=1,
    )[0]
    updates = metadata_payload(fresh)
    revision = hashlib.sha256(
        json.dumps({"metadata": fresh, "model": encoder.model_version}, sort_keys=True).encode()
    ).hexdigest()
    updates.update(
        caption_embedding_status="ready",
        caption_embedding_version=encoder.model_version,
        enrichment_fingerprint=revision,
    )
    async with lock_active_publication(original["video_id"], original["ingestion_run_id"]):
        records = await client.retrieve(
            collection_name=get_settings().qdrant.chunk_collection,
            ids=[point_id],
            with_payload=True,
            with_vectors=True,
        )
        if (
            not records
            or records[0].payload.get("metadata") != original.get("metadata")
            or records[0].payload.get("ingestion_run_id") != original["ingestion_run_id"]
        ):
            raise ValueError("Chunk changed during caption refresh")
        point = records[0]
        # A point upsert publishes caption, evidence and its vector together.
        await client.upsert(
            collection_name=get_settings().qdrant.chunk_collection,
            points=[
                models.PointStruct(
                    id=point.id,
                    payload={**point.payload, **updates},
                    vector={**point.vector, "caption": vector},
                )
            ],
            wait=True,
        )


async def refresh_fallback_captions(
    *,
    video_ids: set[str] | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Refresh incomplete published chunks from their original timestamped VLM sequence."""

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
                scenes.append(await _make_sequence(qdrant, point_id, payload))
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
                            raise ValueError("Sequence enrichment did not succeed")
                        await _write_sequence(qdrant, point_id, dict(batch)[point_id], fresh)
                        updated += 1
                    except Exception as exc:
                        failed += 1
                        failures.append({"point_id": str(point_id), "error": str(exc)[:240]})
                        logger.exception(
                            "Unable to refresh caption for point {point_id}", point_id=point_id
                        )
        finally:
            for scene in scenes:
                for frame in scene.keyframes:
                    frame.close()
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

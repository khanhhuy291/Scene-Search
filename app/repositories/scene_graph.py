"""Validate and transactionally replace a video's semantic scene representation."""

from __future__ import annotations

import hashlib
import json
import math
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select

from core.privacy import is_anonymized_playback, is_anonymized_thumbnail
from db.models.corpus import SceneChunkKeyframe, SceneKeyframe, Segment, SemanticScene, Video
from infrastructure.postgres import get_session_factory
from repositories.corpus import SegmentRow


@dataclass(frozen=True)
class SemanticSceneRow:
    id: UUID
    scene_index: int
    ts_start_s: float
    ts_end_s: float
    boundary_reason: str
    boundary_score: float | None
    ingestion_fingerprint: str


@dataclass(frozen=True)
class SceneKeyframeRow:
    id: UUID
    semantic_scene_id: UUID
    frame_index: int
    timestamp_ms: int
    thumbnail_object_key: str
    privacy_status: str
    ingestion_fingerprint: str


@dataclass(frozen=True)
class MembershipRow:
    segment_id: UUID
    keyframe_id: UUID
    is_representative: bool


@dataclass(frozen=True)
class SceneGraph:
    video_id: UUID
    run_id: str
    fingerprint: str
    scenes: tuple[SemanticSceneRow, ...]
    chunks: tuple[SegmentRow, ...]
    keyframes: tuple[SceneKeyframeRow, ...]
    memberships: tuple[MembershipRow, ...]
    snapshot: dict | None = None


def _bounds(start: float, end: float) -> tuple[int, int]:
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ValueError("Invalid scene graph timestamps")
    return round(start * 1000), round(end * 1000)


def validate_scene_graph(graph: SceneGraph, *, max_duration_s: float) -> None:
    if (
        graph.snapshot is not None
        and hashlib.sha256(
            json.dumps(
                graph.snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
        != graph.fingerprint
    ):
        raise ValueError("Ingestion snapshot does not match its fingerprint")
    if not re.fullmatch(r"[a-f0-9]{64}", graph.fingerprint) or not 0 < len(graph.run_id) <= 64:
        raise ValueError("Invalid ingestion fingerprint or run identity")
    if not math.isfinite(max_duration_s) or max_duration_s <= 0:
        raise ValueError("Invalid chunk duration limit")
    scenes = {row.id: row for row in graph.scenes}
    chunks = {row.id: row for row in graph.chunks}
    frames = {row.id: row for row in graph.keyframes}
    if (
        not scenes
        or not chunks
        or not frames
        or any(
            len(rows) != len(mapping)
            for rows, mapping in (
                (graph.scenes, scenes),
                (graph.chunks, chunks),
                (graph.keyframes, frames),
            )
        )
    ):
        raise ValueError("Scene graph requires nonempty, distinct records")
    if len({row.frame_index for row in graph.keyframes}) != len(frames):
        raise ValueError("Indexed frame references must be unique within a video")
    previous_end = -1
    for index, row in enumerate(graph.scenes):
        start, end = _bounds(row.ts_start_s, row.ts_end_s)
        if row.scene_index != index or start < previous_end:
            raise ValueError("Semantic scenes must be ordered and nonoverlapping")
        if not row.boundary_reason or (
            row.boundary_score is not None and not math.isfinite(row.boundary_score)
        ):
            raise ValueError("Invalid boundary provenance")
        previous_end = end
    for row in (*graph.scenes, *graph.chunks, *graph.keyframes):
        if row.ingestion_fingerprint != graph.fingerprint:
            raise ValueError("Mixed representation identities")
    for row in graph.keyframes:
        parent = scenes.get(row.semantic_scene_id)
        if (
            parent is None
            or row.frame_index < 0
            or not (
                round(parent.ts_start_s * 1000) <= row.timestamp_ms < round(parent.ts_end_s * 1000)
            )
        ):
            raise ValueError("Keyframe is outside its semantic scene")
        if row.privacy_status != "verified" or not is_anonymized_thumbnail(
            row.thumbnail_object_key
        ):
            raise ValueError("Keyframe has no verified derivative")
    per_chunk: dict[UUID, list[MembershipRow]] = {key: [] for key in chunks}
    seen = set()
    used = set()
    for link in graph.memberships:
        chunk, frame = chunks.get(link.segment_id), frames.get(link.keyframe_id)
        if chunk is None or frame is None or (link.segment_id, link.keyframe_id) in seen:
            raise ValueError("Invalid or duplicate keyframe membership")
        if frame.semantic_scene_id != chunk.semantic_scene_id or not (
            round(chunk.ts_start_s * 1000) <= frame.timestamp_ms < round(chunk.ts_end_s * 1000)
        ):
            raise ValueError("Keyframe membership crosses a chunk boundary")
        seen.add((link.segment_id, link.keyframe_id))
        used.add(link.keyframe_id)
        per_chunk[link.segment_id].append(link)
    if used != set(frames):
        raise ValueError("Indexed keyframe has no parent chunk")
    for chunk in graph.chunks:
        start, end = _bounds(chunk.ts_start_s, chunk.ts_end_s)
        parent = scenes.get(chunk.semantic_scene_id)
        if (
            parent is None
            or not parent.ts_start_s <= chunk.ts_start_s < chunk.ts_end_s <= parent.ts_end_s
        ):
            raise ValueError("Retrieval chunk is outside its semantic scene")
        links = per_chunk[chunk.id]
        representatives = [frames[link.keyframe_id] for link in links if link.is_representative]
        if (
            end - start > round(max_duration_s * 1000)
            or chunk.frame_count != len(links)
            or not links
        ):
            raise ValueError("Invalid chunk frame count or duration")
        if len(representatives) != 1 or (
            representatives[0].frame_index != chunk.representative_frame_index
            or representatives[0].timestamp_ms != chunk.representative_timestamp_ms
            or representatives[0].thumbnail_object_key != chunk.thumbnail_object_key
        ):
            raise ValueError("Chunk representative does not match its keyframe membership")
        if chunk.privacy_status != "verified" or not is_anonymized_playback(
            chunk.preview_object_key
        ):
            raise ValueError("Chunk has no verified playback")
    for parent in graph.scenes:
        covered = round(parent.ts_start_s * 1000)
        children = sorted(
            (row for row in graph.chunks if row.semantic_scene_id == parent.id),
            key=lambda row: row.ts_start_s,
        )
        for child in children:
            if round(child.ts_start_s * 1000) > covered:
                raise ValueError("Retrieval chunks leave a semantic scene uncovered")
            covered = max(covered, round(child.ts_end_s * 1000))
        if covered != round(parent.ts_end_s * 1000):
            raise ValueError("Retrieval chunks do not cover the scene tail")


async def preflight_scene_graph(graph: SceneGraph, *, max_duration_s: float) -> None:
    validate_scene_graph(graph, max_duration_s=max_duration_s)
    async with get_session_factory()() as session:
        video = await session.scalar(select(Video).where(Video.id == graph.video_id))
        if video is None or video.ingestion_status != "processing":
            raise ValueError("Video is not reserved for ingestion")
        for model in (SemanticScene, Segment, SceneKeyframe, SceneChunkKeyframe):
            await session.execute(select(model).limit(0))


async def reserve_scene_publication(graph: SceneGraph) -> None:
    """Reserve a writer without touching the serving graph or fingerprint."""
    async with get_session_factory()() as session, session.begin():
        video = await session.scalar(
            select(Video).where(Video.id == graph.video_id).with_for_update()
        )
        if video is None or video.ingestion_status != "processing":
            raise ValueError("Video is not reserved for ingestion")
        if video.ingestion_run_id != graph.run_id:
            raise ValueError("Another ingestion run owns this video's publication")
        if video.active_ingestion_run_id == graph.run_id:
            raise ValueError("Cannot overwrite the serving publication")
        video.ingestion_run_id = graph.run_id


async def assert_ingestion_owner(video_id: UUID, run_id: str) -> None:
    async with get_session_factory()() as session:
        video = await session.scalar(select(Video).where(Video.id == video_id))
        if (
            video is None
            or video.ingestion_status != "processing"
            or video.ingestion_run_id != run_id
        ):
            raise ValueError("Ingestion job no longer owns this video")


async def serving_media(video_id: UUID) -> set[str]:
    async with get_session_factory()() as session:
        chunks = (
            await session.execute(
                select(Segment.thumbnail_object_key, Segment.preview_object_key).where(
                    Segment.video_id == video_id
                )
            )
        ).all()
        thumbnails = (
            await session.scalars(
                select(SceneKeyframe.thumbnail_object_key).where(SceneKeyframe.video_id == video_id)
            )
        ).all()
        return {key for row in chunks for key in row if key} | set(thumbnails)


async def publish_scene_graph(graph: SceneGraph, *, model_version: str) -> None:
    """Switch the SQL graph, media and active vector run in one transaction."""
    async with get_session_factory()() as session, session.begin():
        video = await session.scalar(
            select(Video).where(Video.id == graph.video_id).with_for_update()
        )
        if (
            video is None
            or video.ingestion_status != "processing"
            or video.ingestion_run_id != graph.run_id
        ):
            raise ValueError("Ingestion publication no longer belongs to this run")
        await session.execute(delete(Segment).where(Segment.video_id == graph.video_id))
        await session.execute(delete(SemanticScene).where(SemanticScene.video_id == graph.video_id))
        now = datetime.now(UTC)
        for model, rows in (
            (SemanticScene, graph.scenes),
            (SceneKeyframe, graph.keyframes),
            (Segment, graph.chunks),
        ):
            session.add_all(
                [
                    model(
                        video_id=graph.video_id,
                        **row.__dict__,
                        **({"indexed_at": now} if model is Segment else {}),
                    )
                    for row in rows
                ]
            )
            await session.flush()
        session.add_all([SceneChunkKeyframe(**row.__dict__) for row in graph.memberships])
        video.active_ingestion_run_id = graph.run_id
        video.ingestion_fingerprint = graph.fingerprint
        video.ingestion_snapshot = graph.snapshot
        video.ingestion_status = "indexed"
        video.model_version = model_version
        video.ingested_at = now
        video.preview_object_key = graph.chunks[0].preview_object_key
        video.preview_blurred = True


async def active_publications(video_ids: set[str] | None = None) -> dict[str, str]:
    async with get_session_factory()() as session:
        statement = select(Video.id, Video.active_ingestion_run_id).where(
            Video.active_ingestion_run_id.is_not(None), Video.ingestion_status != "deleting"
        )
        if video_ids is not None:
            statement = statement.where(Video.id.in_([UUID(value) for value in video_ids]))
        return {
            str(identifier): run for identifier, run in (await session.execute(statement)).all()
        }


@asynccontextmanager
async def lock_active_publication(video_id: str, run_id: str):
    """Serialize caption replacement with publication and video deletion."""
    async with get_session_factory()() as session, session.begin():
        video = await session.scalar(
            select(Video).where(Video.id == UUID(video_id)).with_for_update()
        )
        if (
            video is None
            or video.active_ingestion_run_id != run_id
            or video.ingestion_status == "deleting"
        ):
            raise ValueError("Publication is no longer active")
        yield


@asynccontextmanager
async def ingestion_lease(video_id: UUID):
    """Hold a transaction advisory lock through processing, publication and cleanup."""
    from sqlalchemy import text

    from pipelines.common.errors import IngestionBusyError

    key = int.from_bytes(video_id.bytes[:8], "big", signed=True)
    async with get_session_factory()() as session, session.begin():
        acquired = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
        )
        if not acquired:
            raise IngestionBusyError("Video ingestion is already running", stage="acquire")
        yield


async def owns_scene_graph(video_id: UUID, run_id: str) -> bool:
    async with get_session_factory()() as session:
        video = await session.scalar(select(Video).where(Video.id == video_id))
        return (
            video is not None
            and video.ingestion_run_id == run_id
            and video.ingestion_status != "indexed"
        )

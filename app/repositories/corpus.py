"""Transactional persistence boundary for the ingestion corpus."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert

from db.models.corpus import BehaviorEvent, Frame, FrameAttribute, FrameObject, Segment, Video
from db.models.ingestion_task import IngestionTask
from infrastructure.postgres import get_session_factory


@dataclass(frozen=True)
class FrameRow:
    frame_index: int
    ts_start_s: float
    ts_end_s: float
    thumb_object_key: str | None = None
    blurred: bool = True
    blur_region_count: int = 0
    covers_start_s: float | None = None
    covers_end_s: float | None = None
    embedding_model: str | None = None
    model_version: str | None = None


@dataclass(frozen=True)
class SegmentRow:
    segment_index: int
    ts_start_s: float
    ts_end_s: float
    frame_count: int
    keyframe_id: UUID | None = None
    embedding_model: str | None = None
    model_version: str | None = None
    id: UUID | None = None
    preview_object_key: str | None = None
    privacy_status: str = "pending"
    pipeline_version: str | None = None


@dataclass(frozen=True)
class FrameObjectRow:
    frame_id: UUID
    class_name: str
    count: int
    max_conf: float = 1.0
    max_area_ratio: float | None = None
    bbox_summary: dict[str, Any] | None = None


@dataclass(frozen=True)
class FrameAttributeRow:
    frame_id: UUID
    key: str
    value: str
    confidence: float


@dataclass(frozen=True)
class BehaviorEventRow:
    video_id: UUID
    kind: str
    ts_start_s: float
    ts_end_s: float
    frame_id: UUID | None = None
    track_id: str | None = None
    confidence: float = 1.0
    evidence: dict[str, Any] | None = None


@dataclass(frozen=True)
class VideoDeletionPlan:
    celery_task_ids: tuple[str, ...]
    raw_object_key: str | None = None


async def upsert_video(
    *,
    checksum: str,
    source_uri: str,
    dataset: str,
    split: str | None = None,
    external_id: str | None = None,
    media: Any | None = None,
    raw_object_key: str | None = None,
) -> tuple[UUID, bool]:
    """Insert a video reservation or return the existing checksum match."""

    values = {
        "checksum": checksum,
        "source_uri": source_uri,
        "dataset": dataset,
        "split": split,
        "external_id": external_id,
        "raw_object_key": raw_object_key,
        "duration_s": media.duration_s if media else None,
        "fps": media.fps if media else None,
        "width": media.width if media else None,
        "height": media.height if media else None,
        "frame_count": media.frame_count if media else 0,
    }
    factory = get_session_factory()
    async with factory() as session, session.begin():
        statement = (
            insert(Video)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[Video.checksum])
            .returning(Video.id)
        )
        video_id = (await session.execute(statement)).scalar_one_or_none()
        if video_id is not None:
            return video_id, True
        existing = await session.scalar(select(Video.id).where(Video.checksum == checksum))
        if existing is None:  # pragma: no cover - database invariant
            raise RuntimeError("Video checksum conflict did not resolve to an existing row")
        return existing, False


async def set_video_assets(
    video_id: UUID,
    *,
    raw_object_key: str | None = None,
    preview_object_key: str | None = None,
    preview_blurred: bool | None = None,
) -> None:
    values: dict[str, Any] = {}
    if raw_object_key is not None:
        values["raw_object_key"] = raw_object_key
    if preview_object_key is not None:
        values["preview_object_key"] = preview_object_key
    if preview_blurred is not None:
        values["preview_blurred"] = preview_blurred
    if not values:
        return
    factory = get_session_factory()
    async with factory() as session, session.begin():
        await session.execute(update(Video).where(Video.id == video_id).values(**values))


async def is_video_indexed(video_id: UUID) -> bool:
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Video.ingested_at, Video.ingestion_status).where(Video.id == video_id)
        )
        row = result.first()
        if not row:
            return False
        ingested_at, status = row
        return ingested_at is not None and status == "indexed"


async def claim_video_ingestion(video_id: UUID, *, allow_retry: bool = True) -> bool:
    """Atomically reserve a pending, failed, deleting, or retried video for one ingestion task."""
    statuses = (
        ("pending", "failed", "processing", "deleting") if allow_retry else ("pending", "failed")
    )
    factory = get_session_factory()
    async with factory() as session, session.begin():
        result = await session.execute(
            update(Video)
            .where(
                Video.id == video_id,
                Video.ingestion_status.in_(statuses),
            )
            .values(ingestion_status="processing")
        )
        return result.rowcount == 1


async def mark_video_ingestion_failed(video_id: UUID) -> None:
    factory = get_session_factory()
    async with factory() as session, session.begin():
        await session.execute(
            update(Video)
            .where(
                Video.id == video_id,
                Video.ingestion_status.not_in(("indexed", "deleting")),
            )
            .values(ingestion_status="failed")
        )


async def prepare_video_deletion(video_id: UUID) -> VideoDeletionPlan | None:
    """Lock a video against new ingestion and return its external cleanup manifest."""
    factory = get_session_factory()
    async with factory() as session, session.begin():
        video = await session.scalar(select(Video).where(Video.id == video_id).with_for_update())
        if video is None:
            return None
        video.ingestion_status = "deleting"
        celery_ids = list(
            await session.scalars(
                select(IngestionTask.celery_task_id).where(
                    IngestionTask.video_id == video_id,
                    IngestionTask.celery_task_id.is_not(None),
                    IngestionTask.status.in_(("pending", "queued", "processing", "retrying")),
                )
            )
        )
        return VideoDeletionPlan(
            celery_task_ids=tuple(celery_ids), raw_object_key=video.raw_object_key
        )


async def cancel_video_tasks(video_id: UUID) -> None:
    now = datetime.now(UTC)
    factory = get_session_factory()
    async with factory() as session, session.begin():
        await session.execute(
            update(IngestionTask)
            .where(
                IngestionTask.video_id == video_id,
                IngestionTask.status.in_(("pending", "queued", "processing", "retrying")),
            )
            .values(
                status="cancelled",
                error="Video deleted by user",
                error_code="video_deleted",
                finished_at=now,
                updated_at=now,
            )
        )


async def insert_frames(video_id: UUID, frames: Sequence[FrameRow]) -> list[UUID]:
    models = [Frame(video_id=video_id, **row.__dict__) for row in frames]
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add_all(models)
        await session.flush()
        return [model.id for model in models]


async def insert_segments(video_id: UUID, segments: Sequence[SegmentRow]) -> list[UUID]:
    if segments and all(row.id is not None for row in segments):
        values = [
            {
                "video_id": video_id,
                **{key: value for key, value in row.__dict__.items() if value is not None},
            }
            for row in segments
        ]
        statement = insert(Segment).values(values)
        update_columns = {
            column: getattr(statement.excluded, column)
            for column in (
                "ts_start_s",
                "ts_end_s",
                "frame_count",
                "preview_object_key",
                "privacy_status",
                "pipeline_version",
                "embedding_model",
                "model_version",
            )
        }
        statement = statement.on_conflict_do_update(
            index_elements=[Segment.id], set_=update_columns
        ).returning(Segment.id)
        factory = get_session_factory()
        async with factory() as session, session.begin():
            return list((await session.scalars(statement)).all())
    models = [
        Segment(
            video_id=video_id,
            **{key: value for key, value in row.__dict__.items() if value is not None},
        )
        for row in segments
    ]
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add_all(models)
        await session.flush()
        return [model.id for model in models]


async def delete_segments(video_id: UUID) -> None:
    """Remove derived scene metadata so an interrupted run can retry cleanly."""
    factory = get_session_factory()
    async with factory() as session, session.begin():
        await session.execute(delete(Segment).where(Segment.video_id == video_id))


async def get_video_for_pipeline(video_id: UUID) -> Video | None:
    factory = get_session_factory()
    async with factory() as session:
        return await session.scalar(select(Video).where(Video.id == video_id))


async def insert_frame_objects(rows: Sequence[FrameObjectRow]) -> None:
    await _insert_all([FrameObject(**row.__dict__) for row in rows])


async def insert_frame_attributes(rows: Sequence[FrameAttributeRow]) -> None:
    await _insert_all([FrameAttribute(**row.__dict__) for row in rows])


async def insert_behavior_events(rows: Sequence[BehaviorEventRow]) -> None:
    await _insert_all([BehaviorEvent(**row.__dict__) for row in rows])


async def _insert_all(models: Sequence[Any]) -> None:
    if not models:
        return
    factory = get_session_factory()
    async with factory() as session, session.begin():
        session.add_all(models)


async def mark_video_indexed(video_id: UUID, *, model_version: str) -> bool:
    now = datetime.now(UTC)
    factory = get_session_factory()
    async with factory() as session, session.begin():
        result = await session.execute(
            update(Video)
            .where(Video.id == video_id, Video.ingestion_status == "processing")
            .values(
                model_version=model_version,
                ingested_at=now,
                ingestion_status="indexed",
            )
        )
        if result.rowcount != 1:
            return False
        await session.execute(
            update(Frame)
            .where(Frame.video_id == video_id)
            .values(model_version=model_version, indexed_at=now)
        )
        await session.execute(
            update(Segment)
            .where(Segment.video_id == video_id)
            .values(model_version=model_version, indexed_at=now)
        )
        return True


async def delete_video(video_id: UUID) -> None:
    factory = get_session_factory()
    async with factory() as session, session.begin():
        await session.execute(delete(Video).where(Video.id == video_id))


__all__ = [
    "BehaviorEventRow",
    "VideoDeletionPlan",
    "cancel_video_tasks",
    "claim_video_ingestion",
    "FrameAttributeRow",
    "FrameObjectRow",
    "FrameRow",
    "SegmentRow",
    "delete_video",
    "delete_segments",
    "insert_behavior_events",
    "insert_frame_attributes",
    "insert_frame_objects",
    "insert_frames",
    "insert_segments",
    "get_video_for_pipeline",
    "is_video_indexed",
    "mark_video_indexed",
    "mark_video_ingestion_failed",
    "prepare_video_deletion",
    "set_video_assets",
    "upsert_video",
]

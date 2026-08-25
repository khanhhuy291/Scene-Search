"""Corpus tables: videos, frames, and their derived metadata.

A still image is modelled as a ``Video`` holding exactly one ``Frame``; a real
clip uses the same tables with many frames and segments. One schema therefore
serves both media shapes without coupling persistence to a corpus layout.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Video(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One source clip. For the keyframe corpus this holds a single frame."""

    __tablename__ = "videos"

    # Content hash of the source bytes. The unique constraint is what makes
    # ingestion idempotent: re-submitting identical content is a no-op.
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    split: Mapped[str | None] = mapped_column(String(32), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    duration_s: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    fps: Mapped[float | None] = mapped_column(Numeric(8, 3), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # Restricted bucket. No presigned URL is ever issued for this key (ADR-0003).
    raw_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Derived bucket. The anonymized clip, and the only video the API serves.
    preview_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Mirrors frames.blurred at clip level: fail closed, so a clip whose
    # anonymization did not complete is never playable (ADR-0003).
    preview_blurred: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingestion_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )

    frames: Mapped[list[Frame]] = relationship(
        back_populates="video", cascade="all, delete-orphan", passive_deletes=True
    )
    segments: Mapped[list[Segment]] = relationship(
        back_populates="video", cascade="all, delete-orphan", passive_deletes=True
    )
    behavior_events: Mapped[list[BehaviorEvent]] = relationship(
        back_populates="video", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_videos_dataset_split", "dataset", "split"),
        Index("ix_videos_external_id", "external_id"),
        CheckConstraint("frame_count >= 0", name="frame_count_non_negative"),
        CheckConstraint(
            "ingestion_status IN ('pending', 'processing', 'indexed', 'failed', 'deleting')",
            name="ingestion_status_allowed",
        ),
    )


class Frame(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An indexed frame. One row corresponds to one Qdrant point."""

    __tablename__ = "frames"

    video_id: Mapped[UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    ts_start_s: Mapped[float] = mapped_column(Float, nullable=False)
    ts_end_s: Mapped[float] = mapped_column(Float, nullable=False)

    # Derived bucket only. Serving any non-blurred asset is prevented by
    # construction: the asset endpoint accepts derived-bucket keys alone.
    thumb_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Fail closed: a frame whose anonymization step failed is marked false and
    # excluded from every display path (ADR-0003).
    blurred: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    blur_region_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # Near-duplicate folding: a dropped frame's span is merged into the kept
    # frame that represents it, so deduplication never loses time coverage.
    covers_start_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    covers_end_s: Mapped[float | None] = mapped_column(Float, nullable=True)

    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    video: Mapped[Video] = relationship(back_populates="frames")
    objects: Mapped[list[FrameObject]] = relationship(
        back_populates="frame", cascade="all, delete-orphan", passive_deletes=True
    )
    attributes: Mapped[list[FrameAttribute]] = relationship(
        back_populates="frame", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("video_id", "frame_index", name="uq_frames_video_id_frame_index"),
        Index("ix_frames_video_id_ts_start_s", "video_id", "ts_start_s"),
        Index("ix_frames_model_version", "model_version"),
        CheckConstraint("ts_end_s >= ts_start_s", name="timestamps_ordered"),
        CheckConstraint("frame_index >= 0", name="frame_index_non_negative"),
    )


class Segment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A watchable span of a clip, indexed as its own Qdrant point.

    Segment vectors are the mean of their member frame vectors, renormalized.
    They exist so a query can return something playable rather than a still:
    frame granularity answers "which instant", segment granularity answers
    "which few seconds to watch".
    """

    __tablename__ = "segments"

    video_id: Mapped[UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    ts_start_s: Mapped[float] = mapped_column(Float, nullable=False)
    ts_end_s: Mapped[float] = mapped_column(Float, nullable=False)
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Representative frame, used for the segment's poster image.
    keyframe_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("frames.id", ondelete="SET NULL"), nullable=True
    )
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    preview_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    privacy_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending"
    )
    pipeline_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    video: Mapped[Video] = relationship(back_populates="segments")

    __table_args__ = (
        UniqueConstraint("video_id", "segment_index", name="uq_segments_video_id_segment_index"),
        Index("ix_segments_video_id_ts_start_s", "video_id", "ts_start_s"),
        CheckConstraint("ts_end_s >= ts_start_s", name="timestamps_ordered"),
        CheckConstraint("segment_index >= 0", name="segment_index_non_negative"),
        CheckConstraint("frame_count >= 0", name="frame_count_non_negative"),
    )


class FrameObject(UUIDPrimaryKeyMixin, Base):
    """Per-class object summary for a frame.

    Populated from corpus ground-truth boxes rather than a detector pass, so
    ``max_conf`` is 1.0 for label-sourced rows.
    """

    __tablename__ = "frame_objects"

    frame_id: Mapped[UUID] = mapped_column(
        ForeignKey("frames.id", ondelete="CASCADE"), nullable=False
    )
    class_name: Mapped[str] = mapped_column("class", String(64), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    max_conf: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")
    max_area_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    bbox_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    frame: Mapped[Frame] = relationship(back_populates="objects")

    __table_args__ = (
        UniqueConstraint("frame_id", "class", name="uq_frame_objects_frame_id_class"),
        Index("ix_frame_objects_class", "class"),
        CheckConstraint("count >= 0", name="count_non_negative"),
    )


class FrameAttribute(UUIDPrimaryKeyMixin, Base):
    """Scene attribute for a frame: weather, timeofday, or scene."""

    __tablename__ = "frame_attributes"

    frame_id: Mapped[UUID] = mapped_column(
        ForeignKey("frames.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    # 1.0 for dataset labels; below 1.0 only for model-inferred attributes.
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")

    frame: Mapped[Frame] = relationship(back_populates="attributes")

    __table_args__ = (
        UniqueConstraint("frame_id", "key", name="uq_frame_attributes_frame_id_key"),
        Index("ix_frame_attributes_key_value", "key", "value"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )


class BehaviorEvent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A temporal behaviour derived from object tracks (ADR-0002, plan section 5.5)."""

    __tablename__ = "behavior_events"

    video_id: Mapped[UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
    )
    frame_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("frames.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    track_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ts_start_s: Mapped[float] = mapped_column(Float, nullable=False)
    ts_end_s: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")
    # Rule inputs retained so a surprising event can be explained rather than
    # merely trusted.
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    video: Mapped[Video] = relationship(back_populates="behavior_events")

    __table_args__ = (
        Index("ix_behavior_events_kind", "kind"),
        Index("ix_behavior_events_video_id_ts_start_s", "video_id", "ts_start_s"),
        CheckConstraint("ts_end_s >= ts_start_s", name="timestamps_ordered"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )


__all__ = [
    "BehaviorEvent",
    "Frame",
    "FrameAttribute",
    "FrameObject",
    "Segment",
    "Video",
]

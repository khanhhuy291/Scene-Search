"""Create corpus and review tables.

Adds the searchable corpus (videos, frames, objects, attributes, behaviour
events) and the human-in-the-loop review chain (users, review sessions,
decisions, dataset exports).

Revision ID: 20260805_0002
Revises: 20260805_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260805_0002"
down_revision: str | None = "20260805_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("dataset", sa.String(length=64), nullable=False),
        sa.Column("split", sa.String(length=32), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("duration_s", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("fps", sa.Numeric(precision=8, scale=3), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("frame_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("raw_object_key", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("frame_count >= 0", name="frame_count_non_negative"),
        sa.PrimaryKeyConstraint("id", name="pk_videos"),
        sa.UniqueConstraint("checksum", name="uq_videos_checksum"),
    )
    op.create_index("ix_videos_dataset_split", "videos", ["dataset", "split"])
    op.create_index("ix_videos_external_id", "videos", ["external_id"])

    op.create_table(
        "frames",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("ts_start_s", sa.Float(), nullable=False),
        sa.Column("ts_end_s", sa.Float(), nullable=False),
        sa.Column("thumb_object_key", sa.Text(), nullable=True),
        sa.Column("blurred", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("blur_region_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("ts_end_s >= ts_start_s", name="timestamps_ordered"),
        sa.CheckConstraint("frame_index >= 0", name="frame_index_non_negative"),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name="fk_frames_video_id_videos",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_frames"),
        sa.UniqueConstraint("video_id", "frame_index", name="uq_frames_video_id_frame_index"),
    )
    op.create_index("ix_frames_video_id_ts_start_s", "frames", ["video_id", "ts_start_s"])
    op.create_index("ix_frames_model_version", "frames", ["model_version"])

    op.create_table(
        "frame_objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frame_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("class", sa.String(length=64), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_conf", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("max_area_ratio", sa.Float(), nullable=True),
        sa.Column("bbox_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint("count >= 0", name="count_non_negative"),
        sa.ForeignKeyConstraint(
            ["frame_id"],
            ["frames.id"],
            name="fk_frame_objects_frame_id_frames",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_frame_objects"),
        sa.UniqueConstraint("frame_id", "class", name="uq_frame_objects_frame_id_class"),
    )
    op.create_index("ix_frame_objects_class", "frame_objects", ["class"])

    op.create_table(
        "frame_attributes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frame_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("value", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["frame_id"],
            ["frames.id"],
            name="fk_frame_attributes_frame_id_frames",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_frame_attributes"),
        sa.UniqueConstraint("frame_id", "key", name="uq_frame_attributes_frame_id_key"),
    )
    op.create_index("ix_frame_attributes_key_value", "frame_attributes", ["key", "value"])

    op.create_table(
        "behavior_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frame_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("track_id", sa.String(length=64), nullable=True),
        sa.Column("ts_start_s", sa.Float(), nullable=False),
        sa.Column("ts_end_s", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("ts_end_s >= ts_start_s", name="timestamps_ordered"),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name="fk_behavior_events_video_id_videos",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["frame_id"],
            ["frames.id"],
            name="fk_behavior_events_frame_id_frames",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_behavior_events"),
    )
    op.create_index("ix_behavior_events_kind", "behavior_events", ["kind"])
    op.create_index(
        "ix_behavior_events_video_id_ts_start_s", "behavior_events", ["video_id", "ts_start_s"]
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "role IN ('engineer', 'reviewer', 'admin')",
            name="role_allowed",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "review_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("filters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'approved', 'rejected')",
            name="status_allowed",
        ),
        sa.CheckConstraint(
            "(status <> 'approved') OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)",
            name="approved_requires_approver",
        ),
        sa.CheckConstraint(
            "approved_by IS NULL OR approved_by <> created_by",
            name="approver_differs_from_author",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_review_sessions_created_by_users",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name="fk_review_sessions_approved_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_sessions"),
        # Referenced by the composite foreign key from ``datasets``.
        sa.UniqueConstraint("id", "status", name="uq_review_sessions_id_status"),
    )
    op.create_index("ix_review_sessions_status", "review_sessions", ["status"])
    op.create_index("ix_review_sessions_created_by", "review_sessions", ["created_by"])

    op.create_table(
        "review_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frame_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "verdict IN ('relevant', 'irrelevant', 'unsure')",
            name="verdict_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["review_sessions.id"],
            name="fk_review_decisions_session_id_review_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["frame_id"],
            ["frames.id"],
            name="fk_review_decisions_frame_id_frames",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name="fk_review_decisions_decided_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_decisions"),
        sa.UniqueConstraint("session_id", "frame_id", name="uq_review_decisions_session_id_frame_id"),
    )
    op.create_index("ix_review_decisions_verdict", "review_decisions", ["verdict"])

    # The human-in-the-loop gate. ``session_status`` is pinned to 'approved' by a
    # CHECK, and the composite foreign key ties it to the live status of the
    # referenced session, so a row referencing a draft, submitted, or rejected
    # session cannot exist. ON UPDATE RESTRICT also blocks un-approving a session
    # that has already been exported.
    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_status", sa.String(length=16), server_default="approved", nullable=False),
        sa.Column("format", sa.String(length=16), server_default="jsonl", nullable=False),
        sa.Column("manifest_object_key", sa.Text(), nullable=True),
        sa.Column("item_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("exported_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("item_count >= 0", name="item_count_non_negative"),
        sa.CheckConstraint(
            "session_status = 'approved'", name="source_session_approved"
        ),
        sa.CheckConstraint(
            "format IN ('jsonl', 'coco', 'parquet')",
            name="format_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "session_status"],
            ["review_sessions.id", "review_sessions.status"],
            name="fk_datasets_session_id_session_status_review_sessions",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["exported_by"],
            ["users.id"],
            name="fk_datasets_exported_by_users",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_datasets"),
    )
    op.create_index("ix_datasets_session_id", "datasets", ["session_id"])


def downgrade() -> None:
    op.drop_table("datasets")
    op.drop_table("review_decisions")
    op.drop_table("review_sessions")
    op.drop_table("users")
    op.drop_table("behavior_events")
    op.drop_table("frame_attributes")
    op.drop_table("frame_objects")
    op.drop_table("frames")
    op.drop_table("videos")

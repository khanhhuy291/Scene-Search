"""Add segment granularity and anonymized video previews.

Video became a first-class product requirement rather than a later phase, so the
corpus needs two additions: a ``segments`` table holding clip-level vectors that
give a query something watchable to return, and preview asset columns for the
anonymized clip that playback serves.

Revision ID: 20260805_0003
Revises: 20260805_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260805_0003"
down_revision: str | None = "20260805_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The anonymized clip in the derived bucket. ``preview_blurred`` mirrors
    # frames.blurred so playback fails closed the same way display does.
    op.add_column("videos", sa.Column("preview_object_key", sa.Text(), nullable=True))
    op.add_column(
        "videos",
        sa.Column("preview_blurred", sa.Boolean(), server_default="true", nullable=False),
    )

    # Near-duplicate folding. A dropped frame's span is merged into the kept
    # frame representing it, so deduplication reduces cost without losing time
    # coverage.
    op.add_column("frames", sa.Column("covers_start_s", sa.Float(), nullable=True))
    op.add_column("frames", sa.Column("covers_end_s", sa.Float(), nullable=True))

    op.create_table(
        "segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("ts_start_s", sa.Float(), nullable=False),
        sa.Column("ts_end_s", sa.Float(), nullable=False),
        sa.Column("frame_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("keyframe_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("model_version", sa.String(length=64), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("ts_end_s >= ts_start_s", name="timestamps_ordered"),
        sa.CheckConstraint("segment_index >= 0", name="segment_index_non_negative"),
        sa.CheckConstraint("frame_count >= 0", name="frame_count_non_negative"),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name="fk_segments_video_id_videos",
            ondelete="CASCADE",
        ),
        # SET NULL rather than CASCADE: losing the poster frame should not
        # delete the segment, which still has a valid vector and time span.
        sa.ForeignKeyConstraint(
            ["keyframe_id"],
            ["frames.id"],
            name="fk_segments_keyframe_id_frames",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_segments"),
        sa.UniqueConstraint("video_id", "segment_index", name="uq_segments_video_id_segment_index"),
    )
    op.create_index("ix_segments_video_id_ts_start_s", "segments", ["video_id", "ts_start_s"])


def downgrade() -> None:
    op.drop_index("ix_segments_video_id_ts_start_s", table_name="segments")
    op.drop_table("segments")
    op.drop_column("frames", "covers_end_s")
    op.drop_column("frames", "covers_start_s")
    op.drop_column("videos", "preview_blurred")
    op.drop_column("videos", "preview_object_key")

"""Persist semantic scenes, indexed keyframes and chunk membership.

Revision ID: 20261127_0010
Revises: 20261122_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261127_0010"
down_revision: str | None = "20261122_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identity_columns():
    return [
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    op.add_column("videos", sa.Column("ingestion_fingerprint", sa.String(64), nullable=True))
    op.add_column("videos", sa.Column("ingestion_run_id", sa.String(64), nullable=True))
    op.create_table(
        "semantic_scenes",
        *_identity_columns(),
        sa.Column(
            "video_id", sa.UUID(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("scene_index", sa.Integer(), nullable=False),
        sa.Column("ts_start_s", sa.Float(), nullable=False),
        sa.Column("ts_end_s", sa.Float(), nullable=False),
        sa.Column("boundary_reason", sa.String(32), nullable=False),
        sa.Column("boundary_score", sa.Float(), nullable=True),
        sa.Column("pipeline_version", sa.String(64), nullable=False),
        sa.Column("ingestion_fingerprint", sa.String(64), nullable=False),
        sa.UniqueConstraint("video_id", "scene_index", name="uq_semantic_scenes_video_index"),
        sa.CheckConstraint("ts_end_s > ts_start_s AND ts_start_s >= 0", name="timestamps_ordered"),
        sa.CheckConstraint("scene_index >= 0", name="scene_index_non_negative"),
    )
    op.create_index(
        "ix_semantic_scenes_video_id_ts_start_s", "semantic_scenes", ["video_id", "ts_start_s"]
    )
    op.add_column("segments", sa.Column("semantic_scene_id", sa.UUID(), nullable=True))
    op.add_column("segments", sa.Column("ingestion_fingerprint", sa.String(64), nullable=True))
    op.create_foreign_key(
        "fk_segments_semantic_scene_id_semantic_scenes",
        "segments",
        "semantic_scenes",
        ["semantic_scene_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_table(
        "scene_keyframes",
        *_identity_columns(),
        sa.Column(
            "video_id", sa.UUID(), sa.ForeignKey("videos.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "semantic_scene_id",
            sa.UUID(),
            sa.ForeignKey("semantic_scenes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("timestamp_ms", sa.BigInteger(), nullable=False),
        sa.Column("thumbnail_object_key", sa.Text(), nullable=False),
        sa.Column("privacy_status", sa.String(16), nullable=False),
        sa.Column("pipeline_version", sa.String(64), nullable=False),
        sa.Column("ingestion_fingerprint", sa.String(64), nullable=False),
        sa.UniqueConstraint("video_id", "frame_index", name="uq_scene_keyframes_video_frame"),
        sa.CheckConstraint(
            "timestamp_ms >= 0 AND frame_index >= 0", name="frame_reference_non_negative"
        ),
        sa.CheckConstraint("privacy_status = 'verified'", name="privacy_verified"),
    )
    op.create_table(
        "scene_chunk_keyframes",
        sa.Column(
            "segment_id",
            sa.UUID(),
            sa.ForeignKey("segments.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "keyframe_id",
            sa.UUID(),
            sa.ForeignKey("scene_keyframes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("is_representative", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_segments_semantic_scene_id", "segments", ["semantic_scene_id"])
    op.create_index(
        "ix_scene_keyframes_semantic_scene_id", "scene_keyframes", ["semantic_scene_id"]
    )
    op.create_index(
        "ix_scene_chunk_keyframes_keyframe_id", "scene_chunk_keyframes", ["keyframe_id"]
    )


def downgrade() -> None:
    op.drop_table("scene_chunk_keyframes")
    op.drop_table("scene_keyframes")
    op.drop_index("ix_segments_semantic_scene_id", table_name="segments")
    op.drop_constraint(
        "fk_segments_semantic_scene_id_semantic_scenes", "segments", type_="foreignkey"
    )
    op.drop_column("segments", "semantic_scene_id")
    op.drop_column("segments", "ingestion_fingerprint")
    op.drop_index("ix_semantic_scenes_video_id_ts_start_s", table_name="semantic_scenes")
    op.drop_table("semantic_scenes")
    op.drop_column("videos", "ingestion_run_id")
    op.drop_column("videos", "ingestion_fingerprint")

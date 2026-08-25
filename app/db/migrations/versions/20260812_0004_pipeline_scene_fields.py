"""Add scene preview, privacy and pipeline identity fields.

Revision ID: 20260812_0004
Revises: 20260805_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0004"
down_revision: str | None = "20260805_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("segments", sa.Column("preview_object_key", sa.Text(), nullable=True))
    op.add_column(
        "segments",
        sa.Column("privacy_status", sa.String(length=16), server_default="pending", nullable=False),
    )
    op.add_column("segments", sa.Column("pipeline_version", sa.String(length=64), nullable=True))
    op.create_check_constraint(
        "ck_segments_privacy_status",
        "segments",
        "privacy_status IN ('pending', 'verified', 'failed')",
    )
    op.create_index(
        "ix_segments_video_pipeline", "segments", ["video_id", "pipeline_version"]
    )


def downgrade() -> None:
    op.drop_index("ix_segments_video_pipeline", table_name="segments")
    op.drop_constraint("ck_segments_privacy_status", "segments", type_="check")
    op.drop_column("segments", "pipeline_version")
    op.drop_column("segments", "privacy_status")
    op.drop_column("segments", "preview_object_key")

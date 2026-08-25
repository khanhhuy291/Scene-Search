"""Track the ingestion lifecycle on videos.

Revision ID: 20260817_0006
Revises: 20260812_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0006"
down_revision: str | None = "20260812_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "videos",
        sa.Column("ingestion_status", sa.String(16), nullable=False, server_default="pending"),
    )
    op.create_check_constraint(
        "ck_videos_ingestion_status_allowed",
        "videos",
        "ingestion_status IN ('pending', 'processing', 'indexed', 'failed')",
    )
    op.execute("UPDATE videos SET ingestion_status = 'indexed' WHERE ingested_at IS NOT NULL")


def downgrade() -> None:
    op.drop_constraint("ck_videos_ingestion_status_allowed", "videos", type_="check")
    op.drop_column("videos", "ingestion_status")

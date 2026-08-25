"""Allow videos to be locked while deletion is in progress.

Revision ID: 20260817_0007
Revises: 20260817_0006
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260817_0007"
down_revision: str | None = "20260817_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_videos_ingestion_status_allowed", "videos", type_="check")
    op.create_check_constraint(
        "ck_videos_ingestion_status_allowed",
        "videos",
        "ingestion_status IN ('pending', 'processing', 'indexed', 'failed', 'deleting')",
    )


def downgrade() -> None:
    op.execute("UPDATE videos SET ingestion_status = 'failed' WHERE ingestion_status = 'deleting'")
    op.drop_constraint("ck_videos_ingestion_status_allowed", "videos", type_="check")
    op.create_check_constraint(
        "ck_videos_ingestion_status_allowed",
        "videos",
        "ingestion_status IN ('pending', 'processing', 'indexed', 'failed')",
    )

"""Make PostgreSQL ingestion lifecycle explicit and auditable.

Revision ID: 20260812_0005
Revises: 20260812_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260812_0005"
down_revision: str | None = "20260812_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ingestion_tasks", sa.Column("error_code", sa.String(64), nullable=True))
    op.add_column(
        "ingestion_tasks", sa.Column("video_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("ingestion_tasks", sa.Column("celery_task_id", sa.String(64), nullable=True))
    op.add_column("ingestion_tasks", sa.Column("pipeline_version", sa.String(64), nullable=True))
    op.add_column(
        "ingestion_tasks", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "ingestion_tasks", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_ingestion_tasks_video_id_videos",
        "ingestion_tasks",
        "videos",
        ["video_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_ingestion_tasks_video_id", "ingestion_tasks", ["video_id"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_tasks_video_id", table_name="ingestion_tasks")
    op.drop_constraint(
        "fk_ingestion_tasks_video_id_videos", "ingestion_tasks", type_="foreignkey"
    )
    for column in (
        "finished_at",
        "started_at",
        "pipeline_version",
        "celery_task_id",
        "video_id",
        "error_code",
    ):
        op.drop_column("ingestion_tasks", column)

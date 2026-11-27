"""Remove architecture discriminator columns from the single ingestion pipeline."""

import sqlalchemy as sa
from alembic import op

revision = "20261127_0013"
down_revision = "20261127_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_segments_video_pipeline", table_name="segments")
    for table in ("segments", "semantic_scenes", "scene_keyframes", "ingestion_tasks"):
        op.drop_column(table, "pipeline_version")


def downgrade() -> None:
    for table in ("segments", "ingestion_tasks"):
        op.add_column(table, sa.Column("pipeline_version", sa.String(64), nullable=True))
    for table in ("semantic_scenes", "scene_keyframes"):
        op.add_column(
            table,
            sa.Column(
                "pipeline_version", sa.String(64), nullable=False, server_default="scene-ingestion"
            ),
        )
        op.alter_column(table, "pipeline_version", server_default=None)
    op.create_index("ix_segments_video_pipeline", "segments", ["video_id", "pipeline_version"])

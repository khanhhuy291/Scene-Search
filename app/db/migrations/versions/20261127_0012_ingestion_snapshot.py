"""Persist the canonical configuration of the serving publication."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261127_0012"
down_revision = "20261127_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("ingestion_snapshot", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "ingestion_snapshot")

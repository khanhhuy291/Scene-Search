"""Keep the serving publication while its replacement is being built."""

import sqlalchemy as sa
from alembic import op

revision = "20261127_0011"
down_revision = "20261127_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("active_ingestion_run_id", sa.String(64), nullable=True))
    op.execute(
        "UPDATE videos SET active_ingestion_run_id = ingestion_run_id "
        "WHERE ingestion_status = 'indexed' AND ingestion_fingerprint IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("videos", "active_ingestion_run_id")

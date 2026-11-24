"""Persist scene representative references and thumbnail keys.

Revision ID: 20261122_0009
Revises: 20260831_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261122_0009"
down_revision: str | None = "20260831_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("segments", sa.Column("representative_frame_index", sa.Integer(), nullable=True))
    op.add_column(
        "segments", sa.Column("representative_timestamp_ms", sa.BigInteger(), nullable=True)
    )
    op.add_column("segments", sa.Column("thumbnail_object_key", sa.Text(), nullable=True))


def downgrade() -> None:
    for column in (
        "thumbnail_object_key",
        "representative_timestamp_ms",
        "representative_frame_index",
    ):
        op.drop_column("segments", column)

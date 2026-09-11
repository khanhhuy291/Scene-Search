"""Create rlhf_feedback table for reranker fine-tuning.

Revision ID: 20260831_0008
Revises: 20260820_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0008"
down_revision: str | None = "20260820_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rlhf_feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=32), server_default="qwen", nullable=False),
        sa.Column(
            "original_ranking", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "reordered_ranking", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("user_email", sa.String(length=320), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rlhf_feedback_created_at", "rlhf_feedback", ["created_at"], unique=False
    )
    op.create_index("ix_rlhf_feedback_query", "rlhf_feedback", ["query"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_rlhf_feedback_query", table_name="rlhf_feedback")
    op.drop_index("ix_rlhf_feedback_created_at", table_name="rlhf_feedback")
    op.drop_table("rlhf_feedback")

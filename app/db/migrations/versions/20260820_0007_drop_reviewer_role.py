"""Drop the reviewer role; keep engineer and admin only.

Revision ID: 20260820_0007
Revises: 20260819_0006
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260820_0007"
down_revision: str | None = "20260819_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE users SET role = 'engineer' WHERE role = 'reviewer'")
    # Name is the model token (`role_allowed`); Alembic prefixes `ck_users_`.
    op.drop_constraint("role_allowed", "users", type_="check")
    op.create_check_constraint(
        "role_allowed",
        "users",
        "role IN ('engineer', 'admin')",
    )


def downgrade() -> None:
    op.drop_constraint("role_allowed", "users", type_="check")
    op.create_check_constraint(
        "role_allowed",
        "users",
        "role IN ('engineer', 'reviewer', 'admin')",
    )

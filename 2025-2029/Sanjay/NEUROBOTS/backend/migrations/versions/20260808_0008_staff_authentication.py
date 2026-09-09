"""Add persistent medical-staff authentication accounts.

Revision ID: 20260808_0008
Revises: 20260808_0007
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260808_0008"
down_revision: str | None = "20260808_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


staff_role = sa.Enum(
    "DOCTOR", "NURSE", "ADMIN", name="staffrole", native_enum=False
)


def upgrade() -> None:
    op.create_table(
        "staff_users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", staff_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_staff_users_email", "staff_users", ["email"], unique=True)
    op.create_index("ix_staff_users_role", "staff_users", ["role"])
    op.create_index("ix_staff_users_is_active", "staff_users", ["is_active"])


def downgrade() -> None:
    op.drop_table("staff_users")

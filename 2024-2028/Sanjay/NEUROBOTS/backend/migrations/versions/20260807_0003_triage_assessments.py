"""Add append-only prototype triage assessments.

Revision ID: 20260807_0003
Revises: 20260807_0002
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260807_0003"
down_revision: str | None = "20260807_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "triage_assessments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("encounter_id", sa.String(length=36), nullable=False),
        sa.Column("policy_name", sa.String(length=160), nullable=False),
        sa.Column("policy_version", sa.String(length=120), nullable=False),
        sa.Column("severity_level", sa.String(length=80), nullable=False),
        sa.Column("provisional", sa.Boolean(), nullable=False),
        sa.Column("completeness_metadata", sa.JSON(), nullable=False),
        sa.Column("confidence_metadata", sa.JSON(), nullable=False),
        sa.Column("rule_hits", sa.JSON(), nullable=False),
        sa.Column("missing_information", sa.JSON(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("evaluation_latency_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["encounter_id"], ["clinical_encounters.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_triage_assessments_encounter_id",
        "triage_assessments",
        ["encounter_id"],
    )
    op.create_index(
        "ix_triage_assessments_policy_version",
        "triage_assessments",
        ["policy_version"],
    )


def downgrade() -> None:
    op.drop_table("triage_assessments")

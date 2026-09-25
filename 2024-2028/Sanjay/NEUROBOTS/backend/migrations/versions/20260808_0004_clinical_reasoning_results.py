"""Add append-only clinical reasoning results.

Revision ID: 20260808_0004
Revises: 20260807_0003
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260808_0004"
down_revision: str | None = "20260807_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinical_reasoning_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("encounter_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("agent_name", sa.String(length=120), nullable=False),
        sa.Column("agent_version", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("schema_version", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("structured_output", sa.JSON(), nullable=False),
        sa.Column("retrieved_source_ids", sa.JSON(), nullable=False),
        sa.Column("knowledge_graph_evidence", sa.JSON(), nullable=False),
        sa.Column("tool_call_trace", sa.JSON(), nullable=False),
        sa.Column("termination_reason", sa.String(length=80), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["encounter_id"], ["clinical_encounters.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_clinical_reasoning_results_encounter_id",
        "clinical_reasoning_results",
        ["encounter_id"],
    )
    op.create_index(
        "ix_clinical_reasoning_results_workflow_id",
        "clinical_reasoning_results",
        ["workflow_id"],
    )
    op.create_index(
        "ix_clinical_reasoning_results_termination_reason",
        "clinical_reasoning_results",
        ["termination_reason"],
    )


def downgrade() -> None:
    op.drop_table("clinical_reasoning_results")

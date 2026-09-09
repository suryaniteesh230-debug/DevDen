"""Add dynamic priority queue and append-only calculation history.

Revision ID: 20260808_0005
Revises: 20260808_0004
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260808_0005"
down_revision: str | None = "20260808_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


queue_status = sa.Enum(
    "WAITING", "IN_ASSESSMENT", "CALLED", "COMPLETED", "REMOVED",
    name="queuestatus", native_enum=False,
)
priority_band = sa.Enum(
    "CRITICAL", "VERY_HIGH", "HIGH", "MODERATE", "ROUTINE",
    name="priorityband", native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "queue_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("encounter_id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("queue_status", queue_status, nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("priority_band", priority_band, nullable=False),
        sa.Column("policy_name", sa.String(length=160), nullable=False),
        sa.Column("policy_version", sa.String(length=120), nullable=False),
        sa.Column("triage_assessment_id", sa.String(length=36), nullable=False),
        sa.Column("risk_prediction_id", sa.String(length=36), nullable=True),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("rule_trace", sa.JSON(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("deterioration_status", sa.String(length=40), nullable=False),
        sa.Column("waiting_since", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_recalculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["encounter_id"], ["clinical_encounters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triage_assessment_id"], ["triage_assessments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["risk_prediction_id"], ["risk_predictions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("encounter_id"),
    )
    for name, columns in (
        ("ix_queue_entries_encounter_id", ["encounter_id"]),
        ("ix_queue_entries_patient_id", ["patient_id"]),
        ("ix_queue_entries_queue_status", ["queue_status"]),
        ("ix_queue_entries_priority_band", ["priority_band"]),
        ("ix_queue_entries_policy_version", ["policy_version"]),
        ("ix_queue_entries_triage_assessment_id", ["triage_assessment_id"]),
        ("ix_queue_entries_risk_prediction_id", ["risk_prediction_id"]),
        ("ix_queue_entries_waiting_since", ["waiting_since"]),
        ("ix_queue_entries_last_recalculated_at", ["last_recalculated_at"]),
        ("ix_queue_entries_active_order", ["queue_status", "priority_score", "waiting_since", "created_at"]),
    ):
        op.create_index(name, "queue_entries", columns)

    op.create_table(
        "queue_priority_calculations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("queue_entry_id", sa.String(length=36), nullable=False),
        sa.Column("triage_assessment_id", sa.String(length=36), nullable=False),
        sa.Column("risk_prediction_id", sa.String(length=36), nullable=True),
        sa.Column("policy_name", sa.String(length=160), nullable=False),
        sa.Column("policy_version", sa.String(length=120), nullable=False),
        sa.Column("priority_score", sa.Float(), nullable=False),
        sa.Column("priority_band", priority_band, nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("rule_trace", sa.JSON(), nullable=False),
        sa.Column("input_snapshot", sa.JSON(), nullable=False),
        sa.Column("deterioration_status", sa.String(length=40), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["queue_entry_id"], ["queue_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triage_assessment_id"], ["triage_assessments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["risk_prediction_id"], ["risk_predictions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_queue_priority_calculations_queue_entry_id", "queue_priority_calculations", ["queue_entry_id"])
    op.create_index("ix_queue_priority_calculations_triage_assessment_id", "queue_priority_calculations", ["triage_assessment_id"])
    op.create_index("ix_queue_priority_calculations_policy_version", "queue_priority_calculations", ["policy_version"])
    op.create_index("ix_queue_priority_calculations_calculated_at", "queue_priority_calculations", ["calculated_at"])


def downgrade() -> None:
    op.drop_table("queue_priority_calculations")
    op.drop_table("queue_entries")

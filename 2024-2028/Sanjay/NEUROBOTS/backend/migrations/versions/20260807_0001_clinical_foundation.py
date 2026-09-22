"""Create clinical data foundation.

Revision ID: 20260807_0001
Revises:
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260807_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

observation_source = sa.Enum(
    "MANUAL", "SIMULATOR", "OCR", "SPEECH", "EHR", "WEARABLE", name="observationsource"
)
encounter_status = sa.Enum("ACTIVE", "COMPLETED", "CANCELLED", name="encounterstatus")


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("external_patient_id", sa.String(length=64), nullable=False),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("gender", sa.String(length=50), nullable=False),
        sa.Column("phone_number", sa.String(length=30), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_patients_external_patient_id", "patients", ["external_patient_id"], unique=True
    )
    op.create_index("ix_patients_first_name", "patients", ["first_name"])
    op.create_index("ix_patients_last_name", "patients", ["last_name"])

    op.create_table(
        "clinical_encounters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("patient_id", sa.String(length=36), nullable=False),
        sa.Column("encounter_type", sa.String(length=80), nullable=False),
        sa.Column("chief_complaint", sa.Text(), nullable=False),
        sa.Column("clinician_notes", sa.Text(), nullable=True),
        sa.Column("status", encounter_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clinical_encounters_patient_id", "clinical_encounters", ["patient_id"])
    op.create_index("ix_clinical_encounters_status", "clinical_encounters", ["status"])
    op.create_index(
        "ix_encounters_patient_started", "clinical_encounters", ["patient_id", "started_at"]
    )

    op.create_table(
        "symptoms",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("encounter_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=True),
        sa.Column("duration", sa.String(length=100), nullable=True),
        sa.Column("onset", sa.DateTime(timezone=True), nullable=True),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("source", observation_source, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["encounter_id"], ["clinical_encounters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_symptoms_encounter_id", "symptoms", ["encounter_id"])

    op.create_table(
        "vital_signs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("encounter_id", sa.String(length=36), nullable=False),
        sa.Column("heart_rate", sa.Float(), nullable=True),
        sa.Column("systolic_bp", sa.Float(), nullable=True),
        sa.Column("diastolic_bp", sa.Float(), nullable=True),
        sa.Column("spo2", sa.Float(), nullable=True),
        sa.Column("respiratory_rate", sa.Float(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", observation_source, nullable=False),
        sa.ForeignKeyConstraint(["encounter_id"], ["clinical_encounters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_vital_signs_encounter_id", "vital_signs", ["encounter_id"])
    op.create_index(
        "ix_vitals_encounter_measured", "vital_signs", ["encounter_id", "measured_at"]
    )

    op.create_table(
        "lab_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("encounter_id", sa.String(length=36), nullable=False),
        sa.Column("test_name", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=50), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", observation_source, nullable=False),
        sa.Column("reference_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["encounter_id"], ["clinical_encounters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lab_results_encounter_id", "lab_results", ["encounter_id"])
    op.create_index("ix_lab_results_test_name", "lab_results", ["test_name"])
    op.create_index(
        "ix_labs_encounter_collected", "lab_results", ["encounter_id", "collected_at"]
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("encounter_id", sa.String(length=36), nullable=True),
        sa.Column("patient_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["encounter_id"], ["clinical_encounters.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["patient_id"], ["patients.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_encounter_id", "audit_events", ["encounter_id"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])
    op.create_index("ix_audit_events_patient_id", "audit_events", ["patient_id"])
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("lab_results")
    op.drop_table("vital_signs")
    op.drop_table("symptoms")
    op.drop_table("clinical_encounters")
    op.drop_table("patients")

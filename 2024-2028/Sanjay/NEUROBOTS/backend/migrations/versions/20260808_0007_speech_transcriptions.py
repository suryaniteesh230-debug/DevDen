"""Add speech transcription and extracted symptom provenance.

Revision ID: 20260808_0007
Revises: 20260808_0006
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260808_0007"
down_revision: str | None = "20260808_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "speech_transcriptions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("encounter_id", sa.String(length=36), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("safe_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("processing_status", sa.String(length=40), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("confidence_metadata", sa.JSON(), nullable=False),
        sa.Column("extracted_symptoms", sa.JSON(), nullable=False),
        sa.Column("conflicts", sa.JSON(), nullable=False),
        sa.Column("symptom_ids", sa.JSON(), nullable=False),
        sa.Column("transcription_latency_ms", sa.Float(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["encounter_id"], ["clinical_encounters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_speech_transcriptions_encounter_id", "speech_transcriptions", ["encounter_id"])
    op.create_index("ix_speech_transcriptions_sha256", "speech_transcriptions", ["sha256"])
    op.create_index("ix_speech_transcriptions_processing_status", "speech_transcriptions", ["processing_status"])
    op.create_index("ix_speech_transcriptions_processed_at", "speech_transcriptions", ["processed_at"])
    op.create_index("ix_speech_transcriptions_created_at", "speech_transcriptions", ["created_at"])
    op.create_index(
        "ix_speech_transcriptions_encounter_created",
        "speech_transcriptions",
        ["encounter_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("speech_transcriptions")

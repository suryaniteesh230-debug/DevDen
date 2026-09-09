"""Add persisted clinical document OCR results.

Revision ID: 20260808_0006
Revises: 20260808_0005
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260808_0006"
down_revision: str | None = "20260808_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clinical_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("encounter_id", sa.String(length=36), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("safe_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("processing_status", sa.String(length=40), nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=False),
        sa.Column("ocr_engine", sa.String(length=100), nullable=False),
        sa.Column("ocr_engine_version", sa.String(length=120), nullable=False),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("extracted_fields", sa.JSON(), nullable=False),
        sa.Column("conflicts", sa.JSON(), nullable=False),
        sa.Column("lab_result_ids", sa.JSON(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["encounter_id"], ["clinical_encounters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_clinical_documents_encounter_id", "clinical_documents", ["encounter_id"])
    op.create_index("ix_clinical_documents_sha256", "clinical_documents", ["sha256"])
    op.create_index("ix_clinical_documents_processing_status", "clinical_documents", ["processing_status"])
    op.create_index("ix_clinical_documents_processed_at", "clinical_documents", ["processed_at"])
    op.create_index("ix_clinical_documents_created_at", "clinical_documents", ["created_at"])
    op.create_index(
        "ix_clinical_documents_encounter_created",
        "clinical_documents",
        ["encounter_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("clinical_documents")

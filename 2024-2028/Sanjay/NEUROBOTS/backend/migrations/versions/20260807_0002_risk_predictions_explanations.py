"""Add auditable risk predictions and explanations.

Revision ID: 20260807_0002
Revises: 20260807_0001
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260807_0002"
down_revision: str | None = "20260807_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_predictions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("encounter_id", sa.String(length=36), nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=120), nullable=False),
        sa.Column("predicted_class", sa.Integer(), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("input_feature_snapshot", sa.JSON(), nullable=False),
        sa.Column("inference_latency_ms", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["encounter_id"], ["clinical_encounters.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_risk_predictions_encounter_id", "risk_predictions", ["encounter_id"]
    )
    op.create_index(
        "ix_risk_predictions_model_version", "risk_predictions", ["model_version"]
    )

    op.create_table(
        "explanations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("prediction_id", sa.String(length=36), nullable=False),
        sa.Column("explanation_method", sa.String(length=80), nullable=False),
        sa.Column("explainer_version", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=120), nullable=False),
        sa.Column("feature_contributions", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("counterfactual", sa.JSON(), nullable=True),
        sa.Column("clinical_evidence", sa.JSON(), nullable=True),
        sa.Column("saliency", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["prediction_id"], ["risk_predictions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_explanations_prediction_id", "explanations", ["prediction_id"])


def downgrade() -> None:
    op.drop_table("explanations")
    op.drop_table("risk_predictions")

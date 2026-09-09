"""Reproducibly validate the approved dataset and train the Phase 1 model."""

import json
from pathlib import Path

from app.ml.training import train_and_persist


BACKEND_DIR = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    result = train_and_persist(
        dataset_path=BACKEND_DIR / "data" / "raw" / "Heart Attack.csv",
        schema_path=BACKEND_DIR / "ml" / "feature_schema.json",
        artifact_path=(
            BACKEND_DIR / "ml" / "artifacts" / "cardiac_risk_random_forest_v1.0.0.joblib"
        ),
        metadata_path=BACKEND_DIR / "ml" / "model_metadata_v1.0.0.json",
        dataset_report_path=BACKEND_DIR / "ml" / "dataset_report.json",
    )
    print(json.dumps(result, indent=2))

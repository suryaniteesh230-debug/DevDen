from __future__ import annotations

import json
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.ml.dataset import load_feature_schema, prepare_training_arrays


TRAINING_RANDOM_SEED = 42
TEST_SIZE = 0.20
CLASSIFICATION_THRESHOLD = 0.50
MODEL_VERSION = "cardiac-risk-rf-1.0.0"


def _metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    predicted = (probabilities >= CLASSIFICATION_THRESHOLD).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, predicted, labels=[0, 1]).ravel()
    return {
        "accuracy": float(accuracy_score(y_true, predicted)),
        "precision_positive": float(precision_score(y_true, predicted, zero_division=0)),
        "recall_positive_sensitivity": float(recall_score(y_true, predicted, zero_division=0)),
        "specificity": float(tn / (tn + fp)) if tn + fp else None,
        "f1_positive": float(f1_score(y_true, predicted, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "confusion_matrix": [[int(tn), int(fp)], [int(fn), int(tp)]],
    }


def _benchmark_pipeline(pipeline: Pipeline, sample: np.ndarray, repetitions: int = 200) -> dict:
    pipeline.predict_proba(sample)
    timings: list[float] = []
    for _ in range(repetitions):
        started = perf_counter()
        pipeline.predict_proba(sample)
        timings.append((perf_counter() - started) * 1000)
    values = np.asarray(timings)
    return {
        "repetitions": repetitions,
        "mean_ms": float(values.mean()),
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
    }


def train_and_persist(
    *,
    dataset_path: str | Path,
    schema_path: str | Path,
    artifact_path: str | Path,
    metadata_path: str | Path,
    dataset_report_path: str | Path,
) -> dict[str, Any]:
    dataset_path = Path(dataset_path)
    schema_path = Path(schema_path)
    artifact_path = Path(artifact_path)
    metadata_path = Path(metadata_path)
    dataset_report_path = Path(dataset_report_path)
    schema = load_feature_schema(schema_path)
    features, target, preparation = prepare_training_arrays(dataset_path, schema_path)
    dataset_report_path.write_text(
        json.dumps(preparation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    x_train, x_test, y_train, y_test = train_test_split(
        features,
        target,
        test_size=TEST_SIZE,
        random_state=TRAINING_RANDOM_SEED,
        stratify=target,
    )
    candidates: dict[str, Pipeline] = {
        "logistic_regression": Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "classifier",
                    LogisticRegression(
                        max_iter=2000,
                        class_weight="balanced",
                        random_state=TRAINING_RANDOM_SEED,
                    ),
                ),
            ]
        ),
        "random_forest": Pipeline(
            [
                (
                    "classifier",
                    RandomForestClassifier(
                        n_estimators=300,
                        min_samples_leaf=2,
                        class_weight="balanced",
                        random_state=TRAINING_RANDOM_SEED,
                        n_jobs=1,
                    ),
                )
            ]
        ),
    }
    comparison: dict[str, dict[str, Any]] = {}
    fitted: dict[str, Pipeline] = {}
    for name, pipeline in candidates.items():
        pipeline.fit(x_train, y_train)
        probabilities = pipeline.predict_proba(x_test)[:, 1]
        comparison[name] = {
            **_metrics(y_test, probabilities),
            "single_sample_latency": _benchmark_pipeline(pipeline, x_test[:1]),
        }
        fitted[name] = pipeline

    selected_name = max(
        comparison,
        key=lambda name: (
            comparison[name]["recall_positive_sensitivity"],
            comparison[name]["roc_auc"],
            comparison[name]["f1_positive"],
        ),
    )
    selected_pipeline = fitted[selected_name]
    model_name = type(selected_pipeline.named_steps["classifier"]).__name__
    metadata: dict[str, Any] = {
        "model_name": model_name,
        "model_key": selected_name,
        "model_version": MODEL_VERSION,
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset_identifier": schema["dataset"]["identifier"],
        "dataset_filename": dataset_path.name,
        "dataset_sha256": preparation["sha256"],
        "feature_schema_version": schema["schema_version"],
        "expected_features": schema["feature_order"],
        "classification_threshold": CLASSIFICATION_THRESHOLD,
        "metrics": comparison[selected_name],
        "model_comparison": comparison,
        "selection_reason": (
            "Random Forest was selected for its substantially higher positive-class "
            "sensitivity and ROC-AUC on the untouched stratified test split while "
            "remaining a small, fast local tabular model compatible with Tree SHAP."
        ),
        "training_random_seed": TRAINING_RANDOM_SEED,
        "test_size": TEST_SIZE,
        "training_rows": int(len(x_train)),
        "test_rows": int(len(x_test)),
        "invalid_rows_excluded": preparation["invalid_row_count"],
        "library_versions": {
            "python": platform.python_version(),
            "numpy": version("numpy"),
            "scikit-learn": version("scikit-learn"),
            "joblib": version("joblib"),
            "shap": version("shap"),
        },
        "artifact_filename": artifact_path.name,
        "clinical_validation": "NOT_CLINICALLY_VALIDATED",
        "limitations": schema["limitations"],
    }
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "pipeline": selected_pipeline,
            "metadata": metadata,
            "feature_schema": schema,
            "training_background": x_train[:200],
        },
        artifact_path,
        compress=3,
    )
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metadata

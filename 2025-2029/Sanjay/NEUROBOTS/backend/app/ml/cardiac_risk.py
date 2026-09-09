from __future__ import annotations

import math
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.ml.artifact import load_cardiac_artifact


class CardiacRiskTool:
    """Reusable local inference tool with no HTTP or LangGraph dependency."""

    def __init__(self, artifact_path: str | Path | None = None) -> None:
        self.artifact_path = Path(
            artifact_path or get_settings().heart_attack_model_path
        )

    def predict(self, features: dict[str, Any]) -> dict[str, Any]:
        if not self.artifact_path.is_file():
            return {
                "status": "PENDING_CAPABILITY",
                "missing_features": [],
                "reason": f"Model artifact was not found: {self.artifact_path}",
            }
        artifact = load_cardiac_artifact(self.artifact_path)
        metadata = artifact["metadata"]
        expected = metadata["expected_features"]
        missing = [
            name
            for name in expected
            if features.get(name) is None
            or not isinstance(features.get(name), (int, float))
            or not math.isfinite(float(features[name]))
        ]
        if missing:
            return {
                "status": "INCOMPLETE_INPUT",
                "missing_features": missing,
                "input_features": {name: features.get(name) for name in expected},
            }

        numeric_features = {name: float(features[name]) for name in expected}
        schema_features = {
            item["internal_name"]: item for item in artifact["feature_schema"]["features"]
        }
        invalid: list[str] = []
        for name, value in numeric_features.items():
            definition = schema_features[name]
            if "valid_values" in definition and value not in definition["valid_values"]:
                invalid.append(name)
            bounds = definition.get("valid_range", {})
            if "minimum" in bounds and value < bounds["minimum"]:
                invalid.append(name)
            if "exclusive_minimum" in bounds and value <= bounds["exclusive_minimum"]:
                invalid.append(name)
            if "maximum" in bounds and value > bounds["maximum"]:
                invalid.append(name)
        if numeric_features["diastolic_bp"] > numeric_features["systolic_bp"]:
            invalid.extend(["systolic_bp", "diastolic_bp"])
        if invalid:
            return {
                "status": "INVALID_INPUT",
                "invalid_features": list(dict.fromkeys(invalid)),
                "missing_features": [],
                "input_features": {name: features[name] for name in expected},
                "reason": "Feature values violate the declared cardiac schema",
            }

        ordered = np.asarray([[numeric_features[name] for name in expected]], dtype=float)
        started = perf_counter()
        probability = float(artifact["pipeline"].predict_proba(ordered)[0, 1])
        latency_ms = (perf_counter() - started) * 1000
        threshold = float(metadata["classification_threshold"])
        predicted_class = int(probability >= threshold)
        return {
            "status": "SUCCESS",
            "model_name": metadata["model_name"],
            "model_version": metadata["model_version"],
            "feature_schema_version": metadata["feature_schema_version"],
            "probability": probability,
            "predicted_class": predicted_class,
            "prediction": predicted_class,
            "threshold": threshold,
            "input_features": {name: features[name] for name in expected},
            "inference_latency_ms": latency_ms,
            "clinical_validation": metadata["clinical_validation"],
            "disclaimer": (
                "Clinical decision-support prototype only; this model does not "
                "autonomously diagnose myocardial infarction and is not clinically validated."
            ),
        }

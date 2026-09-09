from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import shap

from app.core.config import get_settings
from app.ml.artifact import load_cardiac_artifact


class ShapExplanationTool:
    """Produce model feature contributions for a persisted cardiac model."""

    def __init__(self, artifact_path: str | Path | None = None) -> None:
        self.artifact_path = Path(
            artifact_path or get_settings().heart_attack_model_path
        )
        self.artifact = load_cardiac_artifact(self.artifact_path)
        pipeline = self.artifact["pipeline"]
        self.classifier = pipeline.named_steps["classifier"]
        self.feature_names = self.artifact["metadata"]["expected_features"]
        if self.artifact["metadata"]["model_key"] == "random_forest":
            self.explainer = shap.TreeExplainer(self.classifier)
            self.method = "TreeSHAP"
        else:
            background = pipeline[:-1].transform(self.artifact["training_background"])
            self.explainer = shap.LinearExplainer(self.classifier, background)
            self.method = "LinearSHAP"

    def explain(self, features: dict[str, Any]) -> dict[str, Any]:
        ordered = np.asarray(
            [[float(features[name]) for name in self.feature_names]], dtype=float
        )
        pipeline = self.artifact["pipeline"]
        explain_input = (
            ordered
            if self.artifact["metadata"]["model_key"] == "random_forest"
            else pipeline[:-1].transform(ordered)
        )
        started = perf_counter()
        raw_values = np.asarray(self.explainer.shap_values(explain_input))
        latency_ms = (perf_counter() - started) * 1000
        if raw_values.ndim == 3:
            values = raw_values[0, :, 1]
        elif raw_values.ndim == 2:
            values = raw_values[0]
        else:
            raise ValueError(f"Unexpected SHAP value dimensions: {raw_values.shape}")
        expected = np.asarray(self.explainer.expected_value)
        base_value = float(expected[1] if expected.ndim else expected)
        ranked = sorted(
            (
                {
                    "feature": name,
                    "observed_value": float(features[name]),
                    "shap_value": float(value),
                    "direction": (
                        "INCREASES_POSITIVE_CLASS_OUTPUT"
                        if value > 0
                        else "DECREASES_POSITIVE_CLASS_OUTPUT"
                        if value < 0
                        else "NEUTRAL"
                    ),
                    "magnitude": abs(float(value)),
                }
                for name, value in zip(self.feature_names, values, strict=True)
            ),
            key=lambda item: item["magnitude"],
            reverse=True,
        )
        for rank, contribution in enumerate(ranked, start=1):
            contribution["rank"] = rank
        return {
            "status": "SUCCESS",
            "method": self.method,
            "explainer_version": f"shap-{shap.__version__}",
            "model_version": self.artifact["metadata"]["model_version"],
            "base_value": base_value,
            "feature_contributions": ranked,
            "top_contributors": ranked[:3],
            "explanation_latency_ms": latency_ms,
            "disclaimer": (
                "These are model feature contributions, not proof of clinical causation."
            ),
        }

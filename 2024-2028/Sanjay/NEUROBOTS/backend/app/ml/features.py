from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.workflows.clinical_state import ClinicalState


EXPECTED_CARDIAC_FEATURES = (
    "age",
    "gender",
    "heart_rate",
    "systolic_bp",
    "diastolic_bp",
    "blood_sugar",
    "ck_mb",
    "troponin",
)


@dataclass(slots=True)
class FeatureBuildResult:
    status: str
    features: dict[str, float | int | None]
    missing_features: list[str]
    warnings: list[str] = field(default_factory=list)
    source_snapshot: dict[str, Any] = field(default_factory=dict)


def _age_on(date_of_birth: str, at_time: str) -> int:
    born = date.fromisoformat(date_of_birth)
    observed = datetime.fromisoformat(at_time.replace("Z", "+00:00")).date()
    return observed.year - born.year - (
        (observed.month, observed.day) < (born.month, born.day)
    )


def _encode_gender(value: Any) -> float | None:
    if isinstance(value, (int, float)) and value in (0, 1):
        return float(value)
    normalized = str(value or "").strip().casefold()
    if normalized in {"female", "f", "woman"}:
        return 0.0
    if normalized in {"male", "m", "man"}:
        return 1.0
    return None


def _normal_lab_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def build_cardiac_features(state: ClinicalState) -> FeatureBuildResult:
    fused = state.get("fused_context") or {}
    patient = fused.get("patient") or state.get("patient") or {}
    encounter = fused.get("encounter") or state.get("encounter") or {}
    vital_context = fused.get("vitals") or {}
    current_vitals = vital_context.get("latest") or state.get("current_vitals") or {}
    lab_context = fused.get("labs") or {}
    current_labs = lab_context.get("latest_by_test") or state.get("current_labs") or {}
    current_labs = {_normal_lab_name(key): value for key, value in current_labs.items()}

    age: int | None = None
    if patient.get("date_of_birth") and encounter.get("started_at"):
        age = _age_on(patient["date_of_birth"], encounter["started_at"])
    blood_sugar = current_labs.get("bloodsugar") or current_labs.get("glucose") or {}
    ck_mb = current_labs.get("ckmb") or current_labs.get("creatinekinasemb") or {}
    troponin = current_labs.get("troponin") or {}
    features: dict[str, float | int | None] = {
        "age": age,
        "gender": _encode_gender(patient.get("gender")),
        "heart_rate": current_vitals.get("heart_rate"),
        "systolic_bp": current_vitals.get("systolic_bp"),
        "diastolic_bp": current_vitals.get("diastolic_bp"),
        "blood_sugar": blood_sugar.get("value"),
        "ck_mb": ck_mb.get("value"),
        "troponin": troponin.get("value"),
    }
    missing: list[str] = []
    for name, value in features.items():
        if value is None:
            missing.append(name)
        elif isinstance(value, (int, float)) and not math.isfinite(float(value)):
            features[name] = None
            missing.append(name)
    source_snapshot = {
        "patient_id": patient.get("id"),
        "encounter_id": encounter.get("id"),
        "vitals_id": current_vitals.get("id"),
        "vitals_measured_at": current_vitals.get("measured_at"),
        "vitals_source": current_vitals.get("source"),
        "lab_observations": {
            "blood_sugar": {
                "id": blood_sugar.get("id"),
                "unit": blood_sugar.get("unit"),
                "source": blood_sugar.get("source"),
            },
            "ck_mb": {
                "id": ck_mb.get("id"),
                "unit": ck_mb.get("unit"),
                "source": ck_mb.get("source"),
            },
            "troponin": {
                "id": troponin.get("id"),
                "unit": troponin.get("unit"),
                "source": troponin.get("source"),
            },
        },
    }
    warnings = [
        "Dataset source units are not documented reliably; values were not converted."
    ]
    return FeatureBuildResult(
        status="INCOMPLETE_INPUT" if missing else "COMPLETE",
        features=features,
        missing_features=missing,
        warnings=warnings,
        source_snapshot=source_snapshot,
    )

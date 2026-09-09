from __future__ import annotations

from datetime import datetime, timezone
from math import floor
from time import perf_counter
from typing import Any

from app.core.enums import PriorityBand
from app.priority.deterioration import (
    DETERIORATION_POLICY_VERSION,
    SUPPORTED_FIELDS,
    THRESHOLDS,
    detect_deterioration,
)


POLICY_NAME = "NEUROBOTS Dynamic Priority Policy"
POLICY_VERSION = "dynamic-priority-1.0.0"
POLICY_CREATED_AT = "2026-08-08"

SEVERITY_BASE_SCORES = {
    "CRITICAL": 90.0,
    "VERY_HIGH": 75.0,
    "PROTOTYPE_ESI_2": 75.0,
    "HIGH": 60.0,
    "MODERATE": 40.0,
    "ROUTINE": 20.0,
}

RULE_DEFINITIONS = [
    {"id": "PRIORITY-001", "purpose": "Emergency-severity contribution"},
    {"id": "PRIORITY-002", "purpose": "Supported repeated-vital deterioration"},
    {"id": "PRIORITY-003", "purpose": "Cardiac-model supporting escalation"},
    {"id": "PRIORITY-004", "purpose": "Capped waiting-time adjustment"},
    {"id": "PRIORITY-005", "purpose": "Provisional/missing-information flag"},
]

SUPPORTED_INPUTS = [
    "triage.status",
    "triage.severity_level",
    "triage.prototype_esi_level (kept separate from priority_band)",
    "triage.provisional",
    "triage.assessment_id",
    "cardiac_risk.predicted_class (supporting only)",
    "cardiac_risk.probability threshold (supporting only; never copied into score)",
    "vital_history[-2:] heart_rate/systolic_bp/spo2/respiratory_rate",
    "waiting_since",
]

LIMITATIONS = [
    "Operational ordering policy for a hackathon prototype; not clinically validated.",
    "Requires a successful, determinate upstream triage assessment.",
    "Deterioration uses only two chronological vital readings and fixed explicit deltas.",
    "Cardiac probability is thresholded as one fixed supporting contribution and never becomes the score.",
    "Waiting contributes at most five points and cannot overcome a clearly critical severity tier by itself.",
]


def _as_aware(value: datetime | str) -> datetime:
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _rule(
    rule_id: str,
    *,
    triggered: bool,
    inputs: dict[str, Any],
    contribution: float,
    explanation: str,
) -> dict[str, Any]:
    return {
        "id": rule_id,
        "version": "1.0.0",
        "triggered": triggered,
        "inputs": inputs,
        "contribution": contribution,
        "impact": "SCORE" if contribution else ("FLAG" if triggered else "NONE"),
        "explanation": explanation,
    }


def _band(score: float) -> PriorityBand:
    if score >= 90:
        return PriorityBand.CRITICAL
    if score >= 75:
        return PriorityBand.VERY_HIGH
    if score >= 60:
        return PriorityBand.HIGH
    if score >= 40:
        return PriorityBand.MODERATE
    return PriorityBand.ROUTINE


class DynamicPriorityPolicy:
    policy_name = POLICY_NAME
    policy_version = POLICY_VERSION

    @property
    def metadata(self) -> dict[str, Any]:
        return {
            "policy_name": POLICY_NAME,
            "policy_version": POLICY_VERSION,
            "created_at": POLICY_CREATED_AT,
            "rule_definitions": RULE_DEFINITIONS,
            "severity_base_scores": SEVERITY_BASE_SCORES,
            "deterioration": {
                "policy_version": DETERIORATION_POLICY_VERSION,
                "supported_fields": list(SUPPORTED_FIELDS),
                "thresholds": THRESHOLDS,
            },
            "waiting_time": {
                "points_per_minutes": 30,
                "maximum_points": 5,
            },
            "supported_inputs": SUPPORTED_INPUTS,
            "limitations": LIMITATIONS,
        }

    @staticmethod
    def triage_is_usable(triage: dict[str, Any] | None) -> bool:
        value = triage or {}
        return bool(
            value.get("status") == "SUCCESS"
            and value.get("severity_level") in SEVERITY_BASE_SCORES
            and value.get("assessment_id")
            and value.get("policy_name")
            and value.get("policy_version")
        )

    def calculate(
        self,
        *,
        triage: dict[str, Any],
        cardiac_risk: dict[str, Any] | None,
        vital_history: list[dict[str, Any]] | None,
        waiting_since: datetime | str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        if not self.triage_is_usable(triage):
            return {
                "status": "PENDING_TRIAGE",
                "policy_name": POLICY_NAME,
                "policy_version": POLICY_VERSION,
                "priority_score": None,
                "priority_band": None,
                "reason_codes": [],
                "rule_trace": [],
                "reason": "A successful, determinate, persisted triage assessment is required",
                "calculation_latency_ms": (perf_counter() - started) * 1000,
            }

        current_time = _as_aware(now or datetime.now(timezone.utc))
        waiting_start = _as_aware(waiting_since)
        waiting_minutes = max(0.0, (current_time - waiting_start).total_seconds() / 60)
        severity_level = str(triage["severity_level"])
        severity_contribution = SEVERITY_BASE_SCORES[severity_level]
        deterioration = detect_deterioration(vital_history)
        deterioration_contribution = 15.0 if deterioration["status"] == "DETECTED" else 0.0

        cardiac = cardiac_risk or {}
        cardiac_support = bool(
            cardiac.get("status") == "SUCCESS"
            and cardiac.get("predicted_class") == 1
            and isinstance(cardiac.get("probability"), (int, float))
            and cardiac["probability"] >= 0.8
        )
        cardiac_contribution = 5.0 if cardiac_support else 0.0
        waiting_contribution = float(min(5, floor(waiting_minutes / 30)))
        provisional = bool(triage.get("provisional"))

        rules = [
            _rule(
                "PRIORITY-001",
                triggered=True,
                inputs={
                    "severity_level": severity_level,
                    "prototype_esi_level": triage.get("prototype_esi_level"),
                    "triage_policy": triage.get("policy_name"),
                    "triage_policy_version": triage.get("policy_version"),
                },
                contribution=severity_contribution,
                explanation="Emergency severity supplies the dominant base score.",
            ),
            _rule(
                "PRIORITY-002",
                triggered=deterioration["status"] == "DETECTED",
                inputs=deterioration,
                contribution=deterioration_contribution,
                explanation=(
                    "A supported repeated-vital change increased operational urgency."
                    if deterioration_contribution
                    else "No supported deterioration contribution was applied."
                ),
            ),
            _rule(
                "PRIORITY-003",
                triggered=cardiac_support,
                inputs={
                    "status": cardiac.get("status"),
                    "predicted_class": cardiac.get("predicted_class"),
                    "probability": cardiac.get("probability"),
                    "model_version": cardiac.get("model_version"),
                    "support_threshold": 0.8,
                },
                contribution=cardiac_contribution,
                explanation=(
                    "High cardiac-model output added one fixed supporting escalation."
                    if cardiac_support
                    else "Cardiac output did not meet the fixed supporting threshold."
                ),
            ),
            _rule(
                "PRIORITY-004",
                triggered=waiting_contribution > 0,
                inputs={
                    "waiting_since": waiting_start.isoformat(),
                    "calculated_at": current_time.isoformat(),
                    "waiting_minutes": round(waiting_minutes, 3),
                    "minutes_per_point": 30,
                    "maximum_points": 5,
                },
                contribution=waiting_contribution,
                explanation="Waiting adds one point per 30 minutes, capped at five points.",
            ),
            _rule(
                "PRIORITY-005",
                triggered=provisional,
                inputs={
                    "provisional": provisional,
                    "missing_information": triage.get("missing_information", []),
                },
                contribution=0.0,
                explanation=(
                    "Provisional status is retained as an operational flag without reducing priority."
                    if provisional
                    else "The upstream triage assessment is not marked provisional."
                ),
            ),
        ]
        score = min(
            100.0,
            severity_contribution
            + deterioration_contribution
            + cardiac_contribution
            + waiting_contribution,
        )
        reason_codes = [item["id"] for item in rules if item["triggered"]]
        input_snapshot = {
            "triage_assessment_id": triage.get("assessment_id"),
            "triage": {
                "status": triage.get("status"),
                "severity_level": severity_level,
                "prototype_esi_level": triage.get("prototype_esi_level"),
                "provisional": provisional,
                "policy_name": triage.get("policy_name"),
                "policy_version": triage.get("policy_version"),
            },
            "risk_prediction_id": cardiac.get("prediction_id"),
            "cardiac_risk": {
                "status": cardiac.get("status"),
                "predicted_class": cardiac.get("predicted_class"),
                "probability": cardiac.get("probability"),
                "model_version": cardiac.get("model_version"),
            },
            "deterioration": deterioration,
            "waiting_since": waiting_start.isoformat(),
            "calculated_at": current_time.isoformat(),
        }
        return {
            "status": "SUCCESS",
            "policy_name": POLICY_NAME,
            "policy_version": POLICY_VERSION,
            "priority_score": score,
            "priority_band": _band(score).value,
            "prototype_esi_level": triage.get("prototype_esi_level"),
            "provisional": provisional,
            "deterioration_status": deterioration["status"],
            "deterioration": deterioration,
            "waiting_minutes": round(waiting_minutes, 3),
            "reason_codes": reason_codes,
            "rule_trace": rules,
            "input_snapshot": input_snapshot,
            "calculation_latency_ms": (perf_counter() - started) * 1000,
            "disclaimer": (
                "Operational queue ordering for a hackathon decision-support prototype; "
                "not a diagnosis, validated ESI level, or replacement for clinician judgment."
            ),
        }

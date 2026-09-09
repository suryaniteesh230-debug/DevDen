from __future__ import annotations

from datetime import datetime
from typing import Any


DETERIORATION_POLICY_VERSION = "vital-deterioration-1.0.0"

THRESHOLDS = {
    "heart_rate_rise": 20.0,
    "systolic_bp_drop": 20.0,
    "spo2_drop": 3.0,
    "respiratory_rate_rise": 6.0,
}

SUPPORTED_FIELDS = (
    "heart_rate",
    "systolic_bp",
    "spo2",
    "respiratory_rate",
)


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def detect_deterioration(vital_history: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Compare only the two latest chronological readings and report explicit deltas."""

    readings = [item for item in (vital_history or []) if item.get("measured_at")]
    readings.sort(key=lambda item: (_timestamp(item["measured_at"]), str(item.get("id", ""))))
    if len(readings) < 2:
        return {
            "status": "UNKNOWN",
            "policy_version": DETERIORATION_POLICY_VERSION,
            "reason": "At least two timestamped vital readings are required",
            "signals": [],
            "previous_vital_id": None,
            "latest_vital_id": readings[-1].get("id") if readings else None,
            "comparison": {},
        }

    previous, latest = readings[-2], readings[-1]
    comparison: dict[str, dict[str, float]] = {}
    for field in SUPPORTED_FIELDS:
        previous_value = previous.get(field)
        latest_value = latest.get(field)
        if isinstance(previous_value, (int, float)) and isinstance(latest_value, (int, float)):
            comparison[field] = {
                "previous": float(previous_value),
                "latest": float(latest_value),
                "delta": float(latest_value - previous_value),
            }

    if not comparison:
        return {
            "status": "UNKNOWN",
            "policy_version": DETERIORATION_POLICY_VERSION,
            "reason": "The latest two readings have no comparable supported vital fields",
            "signals": [],
            "previous_vital_id": previous.get("id"),
            "latest_vital_id": latest.get("id"),
            "comparison": {},
        }

    signals: list[dict[str, Any]] = []
    checks = (
        ("heart_rate", "RISE", THRESHOLDS["heart_rate_rise"], "HEART_RATE_RISE"),
        ("systolic_bp", "DROP", THRESHOLDS["systolic_bp_drop"], "SYSTOLIC_BP_DROP"),
        ("spo2", "DROP", THRESHOLDS["spo2_drop"], "SPO2_DROP"),
        (
            "respiratory_rate",
            "RISE",
            THRESHOLDS["respiratory_rate_rise"],
            "RESPIRATORY_RATE_RISE",
        ),
    )
    for field, direction, threshold, signal_id in checks:
        values = comparison.get(field)
        if values is None:
            continue
        delta = values["delta"]
        triggered = delta >= threshold if direction == "RISE" else delta <= -threshold
        if triggered:
            signals.append(
                {
                    "id": signal_id,
                    "field": field,
                    "previous": values["previous"],
                    "latest": values["latest"],
                    "delta": delta,
                    "threshold": threshold,
                    "direction": direction,
                }
            )

    return {
        "status": "DETECTED" if signals else "NOT_DETECTED",
        "policy_version": DETERIORATION_POLICY_VERSION,
        "reason": (
            "One or more supported vital changes crossed a configured threshold"
            if signals
            else "Comparable supported vital changes stayed below configured thresholds"
        ),
        "signals": signals,
        "previous_vital_id": previous.get("id"),
        "latest_vital_id": latest.get("id"),
        "previous_measured_at": str(previous.get("measured_at")),
        "latest_measured_at": str(latest.get("measured_at")),
        "comparison": comparison,
        "thresholds": THRESHOLDS,
    }

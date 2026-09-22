"""Benchmark warmed deterministic triage and combined cardiac/triage fast paths."""

import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import numpy as np

from app.ml.cardiac_risk import CardiacRiskTool
from app.triage.policy import EmergencyTriageTool


BACKEND_DIR = Path(__file__).resolve().parents[1]
CARDIAC_FEATURES = {
    "age": 48,
    "gender": 0.0,
    "heart_rate": 108.0,
    "systolic_bp": 148.0,
    "diastolic_bp": 90.0,
    "blood_sugar": 146.0,
    "ck_mb": 8.4,
    "troponin": 0.18,
}
FUSED_CONTEXT = {
    "patient": {
        "id": "benchmark-patient",
        "date_of_birth": "1978-04-18",
    },
    "encounter": {
        "id": "benchmark-encounter",
        "started_at": "2026-08-07T08:00:00Z",
    },
    "symptoms": [
        {
            "name": "chest pain",
            "present": True,
            "severity": 8,
            "duration": "30 minutes",
        },
        {"name": "shortness of breath", "present": True, "severity": 7},
        {"name": "sweating", "present": True, "severity": 6},
    ],
    "vitals": {
        "latest": {
            "id": "benchmark-vitals",
            "heart_rate": 108.0,
            "systolic_bp": 148.0,
            "diastolic_bp": 90.0,
            "spo2": 95.0,
            "respiratory_rate": 22.0,
            "temperature": 37.1,
        }
    },
}


def summarize(values: list[float]) -> dict:
    samples = np.asarray(values)
    return {
        "repetitions": len(values),
        "mean_ms": float(samples.mean()),
        "p50_ms": float(np.percentile(samples, 50)),
        "p95_ms": float(np.percentile(samples, 95)),
        "minimum_ms": float(samples.min()),
        "maximum_ms": float(samples.max()),
    }


def benchmark() -> dict:
    risk_tool = CardiacRiskTool()
    triage_tool = EmergencyTriageTool()
    cardiac_result = risk_tool.predict(CARDIAC_FEATURES)
    if cardiac_result["status"] != "SUCCESS":
        raise RuntimeError(f"Cardiac fast path unavailable: {cardiac_result}")

    for _ in range(20):
        triage_tool.assess(FUSED_CONTEXT, cardiac_result)
        current_risk = risk_tool.predict(CARDIAC_FEATURES)
        triage_tool.assess(FUSED_CONTEXT, current_risk)

    triage_times: list[float] = []
    for _ in range(1000):
        started = perf_counter()
        triage_tool.assess(FUSED_CONTEXT, cardiac_result)
        triage_times.append((perf_counter() - started) * 1000)

    combined_times: list[float] = []
    for _ in range(500):
        started = perf_counter()
        current_risk = risk_tool.predict(CARDIAC_FEATURES)
        triage_tool.assess(FUSED_CONTEXT, current_risk)
        combined_times.append((perf_counter() - started) * 1000)

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "policy_name": triage_tool.policy_name,
        "policy_version": triage_tool.policy_version,
        "cardiac_model_version": cardiac_result["model_version"],
        "warmup_repetitions": 20,
        "triage_tool": summarize(triage_times),
        "cardiac_plus_triage_tools": summarize(combined_times),
        "combined_target_ms": 500,
        "combined_target_met": float(np.percentile(combined_times, 95)) < 500,
        "excluded_from_measurement": [
            "training",
            "HTTP overhead",
            "LangGraph execution",
            "database persistence",
            "SHAP explanation",
        ],
    }


if __name__ == "__main__":
    result = benchmark()
    output_path = BACKEND_DIR / "triage" / "latency_benchmark.json"
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))

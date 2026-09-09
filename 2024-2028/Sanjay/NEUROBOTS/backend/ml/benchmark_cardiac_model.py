"""Benchmark warmed local inference separately from training, HTTP, and LangGraph."""

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter

import numpy as np
from sqlalchemy.orm import sessionmaker

from app.agents.clinical_agents import TriageRiskAgent
from app.db.base import Base
from app.db.session import build_engine
from app.ml.cardiac_risk import CardiacRiskTool
from app.schemas.clinical import EncounterCreate, PatientCreate
from app.services.encounters import EncounterService
from app.services.patients import PatientService
from app.workflows.clinical_state import create_initial_clinical_state


BACKEND_DIR = Path(__file__).resolve().parents[1]
FEATURES = {
    "age": 52,
    "gender": 0.0,
    "heart_rate": 108.0,
    "systolic_bp": 148.0,
    "diastolic_bp": 90.0,
    "blood_sugar": 146.0,
    "ck_mb": 8.4,
    "troponin": 0.18,
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
    tool = CardiacRiskTool()
    for _ in range(10):
        tool.predict(FEATURES)
    inference_times: list[float] = []
    for _ in range(500):
        started = perf_counter()
        tool.predict(FEATURES)
        inference_times.append((perf_counter() - started) * 1000)

    with tempfile.TemporaryDirectory(prefix="neurobots-risk-benchmark-") as directory:
        engine = build_engine(f"sqlite:///{Path(directory) / 'benchmark.db'}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)
        with Session() as session:
            patient = PatientService(session).create(
                PatientCreate(
                    external_patient_id="BENCHMARK",
                    first_name="Benchmark",
                    last_name="Patient",
                    date_of_birth=date(1974, 5, 12),
                    gender="female",
                )
            )
            encounter = EncounterService(session).create(
                patient.id,
                EncounterCreate(
                    encounter_type="benchmark",
                    chief_complaint="Local inference benchmark",
                    started_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
                ),
            )
            state = create_initial_clinical_state(patient.id, encounter.id)
            state["fused_context"] = {
                "patient": {
                    "id": patient.id,
                    "date_of_birth": "1974-05-12",
                    "gender": "female",
                },
                "encounter": {
                    "id": encounter.id,
                    "started_at": "2026-08-07T00:00:00+00:00",
                },
                "vitals": {
                    "latest": {
                        "id": "benchmark-vitals",
                        "heart_rate": 108.0,
                        "systolic_bp": 148.0,
                        "diastolic_bp": 90.0,
                        "measured_at": "2026-08-07T00:00:00+00:00",
                        "source": "MANUAL",
                    }
                },
                "labs": {
                    "latest_by_test": {
                        "bloodsugar": {"value": 146.0},
                        "ckmb": {"value": 8.4},
                        "troponin": {"value": 0.18},
                    }
                },
            }
            agent = TriageRiskAgent(session, risk_tool=tool)
            agent.run(state)
            agent_times: list[float] = []
            for _ in range(50):
                started = perf_counter()
                agent.run(state)
                agent_times.append((perf_counter() - started) * 1000)
        engine.dispose()

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "model_version": "cardiac-risk-rf-1.0.0",
        "warmup_repetitions": 10,
        "cardiac_risk_tool": summarize(inference_times),
        "triage_risk_agent_with_sqlite_persistence": summarize(agent_times),
        "excluded_from_measurement": [
            "training",
            "HTTP overhead",
            "LangGraph execution",
            "SHAP explanation",
        ],
    }


if __name__ == "__main__":
    result = benchmark()
    (BACKEND_DIR / "ml" / "latency_benchmark.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))

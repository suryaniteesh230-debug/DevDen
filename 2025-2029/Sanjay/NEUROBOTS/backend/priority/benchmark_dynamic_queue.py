"""Benchmark the deterministic queue service and complete local fast path."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, median
from tempfile import TemporaryDirectory
from time import perf_counter

from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import ClinicalEncounter, Patient, TriageAssessment
from app.db.session import build_engine
from app.ml.cardiac_risk import CardiacRiskTool
from app.services.dynamic_queue import DynamicQueueService
from app.triage.policy import EmergencyTriageTool


OUTPUT_PATH = Path(__file__).with_name("latency_benchmark.json")
RUNS = 300


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _summary(values: list[float]) -> dict[str, float | int]:
    return {
        "runs": len(values),
        "mean_ms": round(mean(values), 4),
        "p50_ms": round(median(values), 4),
        "p95_ms": round(_percentile(values, 0.95), 4),
    }


def _context(session: Session) -> tuple[Patient, ClinicalEncounter, dict, dict]:
    patient = Patient(
        external_patient_id="BENCH-QUEUE-001",
        first_name="Benchmark",
        last_name="Queue",
        date_of_birth=date(1962, 1, 1),
        gender="male",
    )
    encounter = ClinicalEncounter(
        patient=patient,
        encounter_type="emergency",
        chief_complaint="Chest pain and dyspnea",
        started_at=datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc),
    )
    assessment = TriageAssessment(
        encounter=encounter,
        policy_name="NEUROBOTS Prototype ESI Subset",
        policy_version="prototype-esi-subset-1.0.0",
        severity_level="PROTOTYPE_ESI_2",
        provisional=True,
        completeness_metadata={},
        confidence_metadata={},
        rule_hits=[],
        missing_information=["full_esi_inputs"],
        input_snapshot={},
        evaluation_latency_ms=0,
    )
    session.add_all([patient, encounter, assessment])
    session.commit()
    fused = {
        "patient": {
            "id": patient.id,
            "date_of_birth": patient.date_of_birth.isoformat(),
        },
        "encounter": {
            "id": encounter.id,
            "started_at": encounter.started_at.isoformat(),
        },
        "symptoms": [
            {"name": "chest pain", "present": True, "severity": 8},
            {"name": "shortness of breath", "present": True, "severity": 7},
        ],
        "vitals": {
            "latest": {
                "id": "vital-2",
                "measured_at": "2026-08-08T11:55:00Z",
                "heart_rate": 108,
                "systolic_bp": 148,
                "diastolic_bp": 90,
                "spo2": 94,
                "respiratory_rate": 24,
            }
        },
    }
    triage = EmergencyTriageTool().assess(fused, None)
    triage["assessment_id"] = assessment.id
    return patient, encounter, triage, fused


def main() -> None:
    with TemporaryDirectory(prefix="neurobots-priority-benchmark-") as directory:
        engine = build_engine(f"sqlite:///{directory}/benchmark.db")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with factory() as session:
            patient, encounter, triage, fused = _context(session)
            service = DynamicQueueService(session)
            cardiac_tool = CardiacRiskTool()
            triage_tool = EmergencyTriageTool()
            features = {
                "age": 64,
                "gender": 1,
                "heart_rate": 108,
                "systolic_bp": 148,
                "diastolic_bp": 90,
                "blood_sugar": 146,
                "ck_mb": 8.4,
                "troponin": 0.18,
            }
            vitals = [
                {
                    "id": "vital-1",
                    "measured_at": "2026-08-08T11:50:00Z",
                    "heart_rate": 105,
                    "systolic_bp": 150,
                    "spo2": 95,
                    "respiratory_rate": 23,
                },
                fused["vitals"]["latest"],
            ]
            now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)

            service.recalculate(
                encounter_id=encounter.id,
                patient_id=patient.id,
                triage=triage,
                cardiac_risk=None,
                vital_history=vitals,
                waiting_since=encounter.started_at,
                now=now,
            )
            warm_cardiac = cardiac_tool.predict(features)
            warm_triage = triage_tool.assess(fused, warm_cardiac)
            warm_triage["assessment_id"] = triage["assessment_id"]
            service.recalculate(
                encounter_id=encounter.id,
                patient_id=patient.id,
                triage=warm_triage,
                cardiac_risk=warm_cardiac,
                vital_history=vitals,
                waiting_since=encounter.started_at,
                now=now,
            )

            queue_latencies: list[float] = []
            for _ in range(RUNS):
                started = perf_counter()
                service.recalculate(
                    encounter_id=encounter.id,
                    patient_id=patient.id,
                    triage=triage,
                    cardiac_risk=None,
                    vital_history=vitals,
                    waiting_since=encounter.started_at,
                    now=now,
                )
                queue_latencies.append((perf_counter() - started) * 1000)

            combined_latencies: list[float] = []
            for _ in range(RUNS):
                started = perf_counter()
                cardiac = cardiac_tool.predict(features)
                assessed = triage_tool.assess(fused, cardiac)
                assessed["assessment_id"] = triage["assessment_id"]
                service.recalculate(
                    encounter_id=encounter.id,
                    patient_id=patient.id,
                    triage=assessed,
                    cardiac_risk=cardiac,
                    vital_history=vitals,
                    waiting_since=encounter.started_at,
                    now=now,
                )
                combined_latencies.append((perf_counter() - started) * 1000)

        engine.dispose()

    result = {
        "benchmark_version": "dynamic-priority-benchmark-1.0.0",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "dynamic_queue_service_with_sqlite_persistence": _summary(queue_latencies),
        "cardiac_risk_plus_emergency_triage_plus_dynamic_queue": _summary(
            combined_latencies
        ),
        "target_ms": 500,
        "excludes": ["HTTP", "LangGraph", "SHAP", "Gemini network latency"],
    }
    OUTPUT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

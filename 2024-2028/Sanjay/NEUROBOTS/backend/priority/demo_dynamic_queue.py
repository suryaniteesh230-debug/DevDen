"""Create four patients, run real workflows, then demonstrate vital-driven reprioritization."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy.orm import sessionmaker

from app.agents.clinical_reasoning_agent import ClinicalReasoningAgent
from app.db.base import Base
from app.db.models import ClinicalEncounter, LabResult, Patient, Symptom, VitalSigns
from app.db.session import build_engine
from app.llm.gemini_provider import GeminiProvider
from app.services.dynamic_queue import DynamicQueueService
from app.workflows.clinical_graph import build_clinical_graph
from app.workflows.clinical_state import create_initial_clinical_state


OUTPUT_PATH = Path(__file__).with_name("dynamic_queue_demo.json")


def _create_case(
    session,
    *,
    external_id: str,
    waiting_minutes: int,
    symptoms: list[str],
    vital_rows: list[dict],
    high_cardiac_inputs: bool,
    reference_time: datetime,
) -> tuple[Patient, ClinicalEncounter]:
    patient = Patient(
        external_patient_id=external_id,
        first_name="Demo",
        last_name=external_id,
        date_of_birth=date(1962, 1, 1),
        gender="male" if external_id in {"QUEUE-A", "QUEUE-C"} else "female",
    )
    encounter = ClinicalEncounter(
        patient=patient,
        encounter_type="emergency",
        chief_complaint=" / ".join(symptoms),
        started_at=reference_time - timedelta(minutes=waiting_minutes),
    )
    session.add_all([patient, encounter])
    session.flush()
    for name in symptoms:
        session.add(
            Symptom(
                encounter=encounter,
                name=name,
                severity=8 if "chest" in name else 6,
                duration="20 minutes",
                present=True,
                source="MANUAL",
            )
        )
    for row in vital_rows:
        session.add(VitalSigns(encounter=encounter, source="MANUAL", **row))
    labs = (
        (("blood sugar", 146.0), ("CK-MB", 8.4), ("troponin", 0.18))
        if high_cardiac_inputs
        else (("blood sugar", 95.0), ("CK-MB", 0.4), ("troponin", 0.001))
    )
    for test_name, value in labs:
        session.add(
            LabResult(
                encounter=encounter,
                test_name=test_name,
                value=value,
                source="MANUAL",
                collected_at=reference_time - timedelta(minutes=2),
            )
        )
    session.commit()
    return patient, encounter


def _run_workflow(session, patient: Patient, encounter: ClinicalEncounter) -> dict:
    unavailable_provider = GeminiProvider(api_key="", model="gemini-3.6-flash")
    graph = build_clinical_graph(
        session,
        clinical_reasoning_agent=ClinicalReasoningAgent(
            session, provider=unavailable_provider
        ),
    )
    return graph.invoke(
        create_initial_clinical_state(patient.id, encounter.id),
        config={"recursion_limit": 32},
    )


def _ordered_queue(
    service: DynamicQueueService, patient_references: dict[str, str]
) -> list[dict]:
    return [
        {
            "rank": rank,
            "patient_reference": patient_references[entry.patient_id],
            "patient_id": entry.patient_id,
            "encounter_id": entry.encounter_id,
            "queue_entry_id": entry.id,
            "priority_score": entry.priority_score,
            "priority_band": entry.priority_band.value,
            "prototype_esi_level": entry.input_snapshot["triage"][
                "prototype_esi_level"
            ],
            "cardiac_probability": entry.input_snapshot["cardiac_risk"][
                "probability"
            ],
            "deterioration_status": entry.deterioration_status,
            "reason_codes": entry.reason_codes,
        }
        for rank, entry in enumerate(service.list(), start=1)
    ]


def main() -> None:
    reference_time = datetime.now(timezone.utc).replace(microsecond=0)
    with TemporaryDirectory(prefix="neurobots-dynamic-queue-demo-") as directory:
        engine = build_engine(f"sqlite:///{directory}/demo.db")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        with factory() as session:
            cases = [
                _create_case(
                    session,
                    external_id="QUEUE-A",
                    waiting_minutes=5,
                    symptoms=["chest pain", "shortness of breath"],
                    vital_rows=[
                        {
                            "heart_rate": 88,
                            "systolic_bp": 132,
                            "diastolic_bp": 82,
                            "spo2": 97,
                            "respiratory_rate": 18,
                            "measured_at": reference_time - timedelta(minutes=3),
                        }
                    ],
                    high_cardiac_inputs=True,
                    reference_time=reference_time,
                ),
                _create_case(
                    session,
                    external_id="QUEUE-B",
                    waiting_minutes=25,
                    symptoms=["chest pain", "shortness of breath"],
                    vital_rows=[
                        {
                            "heart_rate": 78,
                            "systolic_bp": 128,
                            "diastolic_bp": 78,
                            "spo2": 98,
                            "respiratory_rate": 16,
                            "measured_at": reference_time - timedelta(minutes=12),
                        },
                        {
                            "heart_rate": 80,
                            "systolic_bp": 126,
                            "diastolic_bp": 78,
                            "spo2": 98,
                            "respiratory_rate": 17,
                            "measured_at": reference_time - timedelta(minutes=7),
                        },
                    ],
                    high_cardiac_inputs=False,
                    reference_time=reference_time,
                ),
                _create_case(
                    session,
                    external_id="QUEUE-C",
                    waiting_minutes=95,
                    symptoms=["arm discomfort"],
                    vital_rows=[
                        {
                            "heart_rate": 110,
                            "systolic_bp": 145,
                            "diastolic_bp": 88,
                            "spo2": 96,
                            "respiratory_rate": 18,
                            "measured_at": reference_time - timedelta(minutes=4),
                        }
                    ],
                    high_cardiac_inputs=False,
                    reference_time=reference_time,
                ),
                _create_case(
                    session,
                    external_id="QUEUE-D",
                    waiting_minutes=10,
                    symptoms=["chest pain", "sweating"],
                    vital_rows=[
                        {
                            "heart_rate": 84,
                            "systolic_bp": 124,
                            "diastolic_bp": 80,
                            "spo2": 98,
                            "respiratory_rate": 16,
                            "measured_at": reference_time - timedelta(minutes=3),
                        }
                    ],
                    high_cardiac_inputs=False,
                    reference_time=reference_time,
                ),
            ]
            initial_results = {
                patient.external_patient_id: _run_workflow(session, patient, encounter)
                for patient, encounter in cases
            }
            patient_references = {
                patient.id: patient.external_patient_id for patient, _ in cases
            }
            service = DynamicQueueService(session)
            initial_queue = _ordered_queue(service, patient_references)

            patient_b, encounter_b = cases[1]
            worsening = VitalSigns(
                encounter=encounter_b,
                heart_rate=108,
                systolic_bp=100,
                diastolic_bp=68,
                spo2=94,
                respiratory_rate=24,
                measured_at=reference_time - timedelta(minutes=1),
                source="MANUAL",
            )
            session.add(worsening)
            session.commit()
            session.expire_all()
            reassessed_b = _run_workflow(session, patient_b, encounter_b)
            updated_queue = _ordered_queue(service, patient_references)
            priority_trace = reassessed_b["priority"]["rule_trace"]

            result = {
                "demo_version": "dynamic-priority-demo-1.0.0",
                "policy_name": reassessed_b["priority"]["policy_name"],
                "policy_version": reassessed_b["priority"]["policy_version"],
                "initial_queue": initial_queue,
                "updated_queue": updated_queue,
                "reassessment": {
                    "patient_reference": patient_b.external_patient_id,
                    "previous_triage_assessment_id": initial_results["QUEUE-B"][
                        "triage"
                    ]["assessment_id"],
                    "new_triage_assessment_id": reassessed_b["triage"][
                        "assessment_id"
                    ],
                    "previous_priority_score": initial_results["QUEUE-B"][
                        "priority"
                    ]["priority_score"],
                    "new_priority_score": reassessed_b["priority"][
                        "priority_score"
                    ],
                    "deterioration_status": reassessed_b["priority"][
                        "deterioration_status"
                    ],
                    "new_vital_id": worsening.id,
                    "priority_rule_trace": priority_trace,
                },
            }
        engine.dispose()

    OUTPUT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

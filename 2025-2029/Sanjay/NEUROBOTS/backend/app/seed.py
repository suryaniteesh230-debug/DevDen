from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.agents.clinical_reasoning_agent import ClinicalReasoningAgent
from app.core.enums import EncounterStatus, ObservationSource
from app.db.models import LabResult, QueueEntry, Symptom, VitalSigns
from app.db.session import SessionLocal
from app.llm.gemini_provider import GeminiProvider
from app.schemas.clinical import (
    EncounterCreate,
    LabResultCreate,
    PatientCreate,
    SymptomCreate,
    VitalSignsCreate,
)
from app.services.encounters import EncounterService
from app.services.observations import ObservationService
from app.services.patients import PatientService
from app.workflows.clinical_graph import build_clinical_graph
from app.workflows.clinical_state import create_initial_clinical_state


HISTORICAL_ENCOUNTER_START = datetime(2026, 7, 10, 9, 30, tzinfo=timezone.utc)
HISTORICAL_ENCOUNTER_END = datetime(2026, 7, 10, 11, 0, tzinfo=timezone.utc)
CURRENT_ENCOUNTER_START = datetime(2026, 8, 8, 9, 0, tzinfo=timezone.utc)
HISTORICAL_MARKER = "Deterministic demonstration history"
LEGACY_CURRENT_MARKER = "Deterministic synthetic judge scenario"
CURRENT_MARKER = "Deterministic synthetic demo scenario v2"


def _at(hour: int, minute: int) -> datetime:
    return datetime(2026, 8, 8, hour, minute, tzinfo=timezone.utc)


def _before(hour: int, minute: int, **delta: int) -> datetime:
    return _at(hour, minute) - timedelta(**delta)


DEMO_CASES = (
    {
        "external_patient_id": "DEMO-001",
        "first_name": "Asha",
        "last_name": "Rao",
        "date_of_birth": "1974-05-12",
        "gender": "female",
        "phone_number": "555-0101",
        "scenario": "suspected acute coronary syndrome",
        "chief_complaint": "Chest pressure, shortness of breath, and sweating",
        "started_at": CURRENT_ENCOUNTER_START,
        "symptoms": (
            {
                "name": "chest pain",
                "severity": 8,
                "duration": "30 minutes",
                "onset": _before(9, 0, minutes=30),
            },
            {
                "name": "shortness of breath",
                "severity": 7,
                "duration": "20 minutes",
                "onset": _before(9, 0, minutes=20),
            },
            {
                "name": "sweating",
                "severity": 6,
                "duration": "15 minutes",
                "onset": _before(9, 0, minutes=15),
            },
        ),
        "vitals": (
            {
                "heart_rate": 96,
                "systolic_bp": 142,
                "diastolic_bp": 88,
                "spo2": 96,
                "respiratory_rate": 20,
                "temperature": 37.0,
                "measured_at": _at(9, 12),
            },
            {
                "heart_rate": 122,
                "systolic_bp": 118,
                "diastolic_bp": 76,
                "spo2": 92,
                "respiratory_rate": 28,
                "temperature": 37.1,
                "measured_at": _at(9, 27),
            },
        ),
        "labs": (
            {
                "test_name": "blood sugar",
                "value": 158.0,
                "unit": "mg/dL",
                "collected_at": _at(9, 35),
            },
            {"test_name": "CK-MB", "value": 7.6, "unit": "ng/mL", "collected_at": _at(9, 35)},
            {"test_name": "troponin", "value": 0.42, "unit": "ng/mL", "collected_at": _at(9, 35)},
        ),
    },
    {
        "external_patient_id": "DEMO-002",
        "first_name": "Vikram",
        "last_name": "Singh",
        "date_of_birth": "1988-09-23",
        "gender": "male",
        "phone_number": None,
        "scenario": "chest-wall strain presentation",
        "chief_complaint": "Sharp chest pain after lifting, worse with movement",
        "started_at": _at(9, 20),
        "symptoms": (
            {"name": "chest pain", "severity": 5, "duration": "2 hours", "onset": _at(7, 20)},
            {
                "name": "chest wall tenderness",
                "severity": 5,
                "duration": "2 hours",
                "onset": _at(7, 20),
            },
        ),
        "vitals": (
            {
                "heart_rate": 82,
                "systolic_bp": 126,
                "diastolic_bp": 78,
                "spo2": 99,
                "respiratory_rate": 16,
                "temperature": 36.8,
                "measured_at": _at(9, 30),
            },
        ),
        "labs": (
            {
                "test_name": "blood sugar",
                "value": 96.0,
                "unit": "mg/dL",
                "collected_at": _at(9, 45),
            },
            {"test_name": "CK-MB", "value": 1.4, "unit": "ng/mL", "collected_at": _at(9, 45)},
            {"test_name": "troponin", "value": 0.006, "unit": "ng/mL", "collected_at": _at(9, 45)},
        ),
    },
    {
        "external_patient_id": "DEMO-003",
        "first_name": "Leena",
        "last_name": "Das",
        "date_of_birth": "1962-02-14",
        "gender": "female",
        "phone_number": None,
        "scenario": "symptomatic tachyarrhythmia",
        "chief_complaint": "Dizziness and palpitations",
        "started_at": _at(9, 35),
        "symptoms": (
            {"name": "dizziness", "severity": 6, "duration": "25 minutes", "onset": _at(9, 10)},
            {"name": "palpitations", "severity": 7, "duration": "25 minutes", "onset": _at(9, 10)},
        ),
        "vitals": (
            {
                "heart_rate": 138,
                "systolic_bp": 104,
                "diastolic_bp": 68,
                "spo2": 97,
                "respiratory_rate": 22,
                "temperature": 36.9,
                "measured_at": _at(9, 42),
            },
        ),
        "labs": (
            {
                "test_name": "blood sugar",
                "value": 104.0,
                "unit": "mg/dL",
                "collected_at": _at(9, 52),
            },
            {"test_name": "CK-MB", "value": 1.1, "unit": "ng/mL", "collected_at": _at(9, 52)},
            {"test_name": "troponin", "value": 0.006, "unit": "ng/mL", "collected_at": _at(9, 52)},
            {"test_name": "potassium", "value": 3.3, "unit": "mmol/L", "collected_at": _at(9, 52)},
        ),
    },
    {
        "external_patient_id": "DEMO-004",
        "first_name": "Omar",
        "last_name": "Khan",
        "date_of_birth": "1995-11-02",
        "gender": "male",
        "phone_number": None,
        "scenario": "acute asthma exacerbation",
        "chief_complaint": "Wheezing, chest tightness, and shortness of breath",
        "started_at": _at(9, 50),
        "symptoms": (
            {"name": "wheezing", "severity": 7, "duration": "3 hours", "onset": _at(6, 50)},
            {
                "name": "shortness of breath",
                "severity": 8,
                "duration": "3 hours",
                "onset": _at(6, 50),
            },
            {"name": "chest tightness", "severity": 6, "duration": "3 hours", "onset": _at(6, 50)},
        ),
        "vitals": (
            {
                "heart_rate": 114,
                "systolic_bp": 128,
                "diastolic_bp": 76,
                "spo2": 90,
                "respiratory_rate": 32,
                "temperature": 36.8,
                "measured_at": _at(9, 55),
            },
        ),
        "labs": (
            {
                "test_name": "peak expiratory flow",
                "value": 170.0,
                "unit": "L/min",
                "collected_at": _at(10, 0),
            },
        ),
    },
    {
        "external_patient_id": "DEMO-005",
        "first_name": "Maya",
        "last_name": "Patel",
        "date_of_birth": "2017-04-19",
        "gender": "female",
        "phone_number": None,
        "scenario": "febrile lower-respiratory infection",
        "chief_complaint": "High fever, productive cough, and difficulty breathing",
        "started_at": _at(10, 5),
        "symptoms": (
            {"name": "fever", "severity": 8, "duration": "2 days", "onset": _before(10, 5, days=2)},
            {
                "name": "productive cough",
                "severity": 7,
                "duration": "3 days",
                "onset": _before(10, 5, days=3),
            },
            {
                "name": "shortness of breath",
                "severity": 6,
                "duration": "6 hours",
                "onset": _before(10, 5, hours=6),
            },
        ),
        "vitals": (
            {
                "heart_rate": 126,
                "systolic_bp": 104,
                "diastolic_bp": 66,
                "spo2": 92,
                "respiratory_rate": 30,
                "temperature": 39.2,
                "measured_at": _at(10, 12),
            },
        ),
        "labs": (
            {
                "test_name": "white blood cell count",
                "value": 15.4,
                "unit": "10^9/L",
                "collected_at": _at(10, 28),
            },
            {
                "test_name": "C-reactive protein",
                "value": 68.0,
                "unit": "mg/L",
                "collected_at": _at(10, 28),
            },
        ),
    },
    {
        "external_patient_id": "DEMO-006",
        "first_name": "Joseph",
        "last_name": "D'Souza",
        "date_of_birth": "1951-12-07",
        "gender": "male",
        "phone_number": None,
        "scenario": "gastroenteritis with dehydration",
        "chief_complaint": "Vomiting, diarrhea, weakness, and reduced fluid intake",
        "started_at": _at(10, 20),
        "symptoms": (
            {
                "name": "vomiting",
                "severity": 7,
                "duration": "18 hours",
                "onset": _before(10, 20, hours=18),
            },
            {
                "name": "diarrhea",
                "severity": 7,
                "duration": "24 hours",
                "onset": _before(10, 20, hours=24),
            },
            {
                "name": "weakness",
                "severity": 6,
                "duration": "12 hours",
                "onset": _before(10, 20, hours=12),
            },
        ),
        "vitals": (
            {
                "heart_rate": 112,
                "systolic_bp": 92,
                "diastolic_bp": 58,
                "spo2": 97,
                "respiratory_rate": 22,
                "temperature": 37.8,
                "measured_at": _at(10, 27),
            },
        ),
        "labs": (
            {"test_name": "sodium", "value": 147.0, "unit": "mmol/L", "collected_at": _at(10, 42)},
            {"test_name": "creatinine", "value": 1.5, "unit": "mg/dL", "collected_at": _at(10, 42)},
            {
                "test_name": "blood sugar",
                "value": 112.0,
                "unit": "mg/dL",
                "collected_at": _at(10, 42),
            },
        ),
    },
    {
        "external_patient_id": "DEMO-007",
        "first_name": "Kavya",
        "last_name": "Iyer",
        "date_of_birth": "1983-06-28",
        "gender": "female",
        "phone_number": None,
        "scenario": "symptomatic hypoglycemia",
        "chief_complaint": "Confusion, sweating, and tremor after missing a meal",
        "started_at": _at(10, 35),
        "symptoms": (
            {"name": "confusion", "severity": 7, "duration": "20 minutes", "onset": _at(10, 15)},
            {"name": "sweating", "severity": 6, "duration": "30 minutes", "onset": _at(10, 5)},
            {"name": "tremor", "severity": 6, "duration": "30 minutes", "onset": _at(10, 5)},
        ),
        "vitals": (
            {
                "heart_rate": 108,
                "systolic_bp": 134,
                "diastolic_bp": 78,
                "spo2": 98,
                "respiratory_rate": 18,
                "temperature": 36.4,
                "measured_at": _at(10, 39),
            },
        ),
        "labs": (
            {
                "test_name": "blood sugar",
                "value": 48.0,
                "unit": "mg/dL",
                "collected_at": _at(10, 40),
            },
        ),
    },
    {
        "external_patient_id": "DEMO-008",
        "first_name": "Arjun",
        "last_name": "Nair",
        "date_of_birth": "1998-10-11",
        "gender": "non-binary",
        "phone_number": None,
        "scenario": "renal-colic presentation",
        "chief_complaint": "Sudden severe left flank pain radiating to the groin",
        "started_at": _at(10, 50),
        "symptoms": (
            {"name": "flank pain", "severity": 9, "duration": "90 minutes", "onset": _at(9, 20)},
            {"name": "nausea", "severity": 6, "duration": "60 minutes", "onset": _at(9, 50)},
            {
                "name": "blood in urine",
                "severity": 3,
                "duration": "1 episode",
                "onset": _at(10, 20),
            },
        ),
        "vitals": (
            {
                "heart_rate": 106,
                "systolic_bp": 152,
                "diastolic_bp": 92,
                "spo2": 99,
                "respiratory_rate": 20,
                "temperature": 37.0,
                "measured_at": _at(10, 56),
            },
        ),
        "labs": (
            {
                "test_name": "urine red blood cells",
                "value": 50.0,
                "unit": "cells/HPF",
                "collected_at": _at(11, 8),
            },
            {"test_name": "creatinine", "value": 1.0, "unit": "mg/dL", "collected_at": _at(11, 8)},
        ),
    },
    {
        "external_patient_id": "DEMO-009",
        "first_name": "Harpreet",
        "last_name": "Kaur",
        "date_of_birth": "1967-03-16",
        "gender": "female",
        "phone_number": None,
        "scenario": "severe hypertension with neurologic symptoms",
        "chief_complaint": "Severe headache, blurred vision, and nausea",
        "started_at": _at(11, 5),
        "symptoms": (
            {"name": "headache", "severity": 8, "duration": "4 hours", "onset": _at(7, 5)},
            {"name": "blurred vision", "severity": 6, "duration": "2 hours", "onset": _at(9, 5)},
            {"name": "nausea", "severity": 4, "duration": "1 hour", "onset": _at(10, 5)},
        ),
        "vitals": (
            {
                "heart_rate": 88,
                "systolic_bp": 212,
                "diastolic_bp": 116,
                "spo2": 98,
                "respiratory_rate": 18,
                "temperature": 36.7,
                "measured_at": _at(11, 10),
            },
        ),
        "labs": (
            {"test_name": "creatinine", "value": 1.4, "unit": "mg/dL", "collected_at": _at(11, 25)},
            {
                "test_name": "blood sugar",
                "value": 118.0,
                "unit": "mg/dL",
                "collected_at": _at(11, 25),
            },
        ),
    },
    {
        "external_patient_id": "DEMO-010",
        "first_name": "Tenzin",
        "last_name": "Dolma",
        "date_of_birth": "2005-09-02",
        "gender": "female",
        "phone_number": None,
        "scenario": "acute ankle injury",
        "chief_complaint": "Ankle pain, swelling, and inability to bear weight after a fall",
        "started_at": _at(11, 20),
        "symptoms": (
            {"name": "ankle pain", "severity": 7, "duration": "45 minutes", "onset": _at(10, 35)},
            {
                "name": "ankle swelling",
                "severity": 6,
                "duration": "40 minutes",
                "onset": _at(10, 40),
            },
            {
                "name": "inability to bear weight",
                "severity": 7,
                "duration": "45 minutes",
                "onset": _at(10, 35),
            },
        ),
        "vitals": (
            {
                "heart_rate": 92,
                "systolic_bp": 118,
                "diastolic_bp": 74,
                "spo2": 99,
                "respiratory_rate": 16,
                "temperature": 36.6,
                "measured_at": _at(11, 25),
            },
        ),
        "labs": (),
    },
)


def _patient_for_case(session, patients: PatientService, case: dict):
    matches = patients.search(case["external_patient_id"], None, 1)
    if matches:
        patient = matches[0]
        payload = PatientCreate(
            external_patient_id=case["external_patient_id"],
            first_name=case["first_name"],
            last_name=case["last_name"],
            date_of_birth=case["date_of_birth"],
            gender=case["gender"],
            phone_number=case["phone_number"],
        )
        changed = False
        for field in ("first_name", "last_name", "date_of_birth", "gender", "phone_number"):
            value = getattr(payload, field)
            if getattr(patient, field) != value:
                setattr(patient, field, value)
                changed = True
        if changed:
            session.commit()
            session.refresh(patient)
        return patient
    return patients.create(
        PatientCreate(
            external_patient_id=case["external_patient_id"],
            first_name=case["first_name"],
            last_name=case["last_name"],
            date_of_birth=case["date_of_birth"],
            gender=case["gender"],
            phone_number=case["phone_number"],
        ),
        actor="development-seed",
    )


def _encounter_with_marker(
    patients: PatientService, patient_id: str, markers: str | tuple[str, ...]
):
    _patient, history = patients.history(patient_id)
    accepted = (markers,) if isinstance(markers, str) else markers
    return next(
        (
            item
            for item in history
            if item.clinician_notes
            and any(item.clinician_notes.startswith(marker) for marker in accepted)
        ),
        None,
    )


def _current_notes(case: dict) -> str:
    return (
        f"{CURRENT_MARKER}; working concern: {case['scenario']}. "
        "Synthetic demonstration only; not a confirmed diagnosis."
    )


def _same_value(actual, expected) -> bool:
    if isinstance(actual, datetime) and isinstance(expected, datetime):
        actual_utc = actual.replace(tzinfo=timezone.utc) if actual.tzinfo is None else actual
        expected_utc = (
            expected.replace(tzinfo=timezone.utc)
            if expected.tzinfo is None
            else expected
        )
        return actual_utc.astimezone(timezone.utc) == expected_utc.astimezone(timezone.utc)
    return actual == expected


def _rows_match(actual: list, expected: tuple[dict, ...], fields: tuple[str, ...]) -> bool:
    return len(actual) == len(expected) and all(
        all(
            _same_value(
                getattr(row, field),
                values.get(field, True if field == "present" else None),
            )
            for field in fields
        )
        and row.source == ObservationSource.MANUAL
        for row, values in zip(actual, expected, strict=True)
    )


def _case_matches(session, encounter, case: dict) -> bool:
    observations = ObservationService(session)
    encounter_fields_match = (
        encounter.encounter_type == "emergency"
        and encounter.chief_complaint == case["chief_complaint"]
        and encounter.clinician_notes == _current_notes(case)
        and encounter.status == EncounterStatus.ACTIVE
        and encounter.completed_at is None
        and _same_value(encounter.started_at, case["started_at"])
    )
    return encounter_fields_match and all(
        (
            _rows_match(
                observations.list_symptoms(encounter.id),
                case["symptoms"],
                ("name", "severity", "duration", "onset", "present"),
            ),
            _rows_match(
                observations.list_vitals(encounter.id),
                case["vitals"],
                (
                    "heart_rate",
                    "systolic_bp",
                    "diastolic_bp",
                    "spo2",
                    "respiratory_rate",
                    "temperature",
                    "measured_at",
                ),
            ),
            _rows_match(
                observations.list_labs(encounter.id),
                case["labs"],
                ("test_name", "value", "unit", "collected_at"),
            ),
        )
    )


def _seed_historical_encounter(session, patients: PatientService, patient_id: str) -> None:
    if _encounter_with_marker(patients, patient_id, HISTORICAL_MARKER) is not None:
        return
    encounter = EncounterService(session).create(
        patient_id,
        EncounterCreate(
            encounter_type="urgent-care",
            chief_complaint="Prior episode of chest discomfort",
            clinician_notes=HISTORICAL_MARKER,
            status=EncounterStatus.COMPLETED,
            started_at=HISTORICAL_ENCOUNTER_START,
            completed_at=HISTORICAL_ENCOUNTER_END,
        ),
        actor="development-seed",
    )
    observations = ObservationService(session)
    observations.add_symptom(
        encounter.id,
        SymptomCreate(
            name="chest discomfort",
            severity=4,
            duration="20 minutes",
            source=ObservationSource.MANUAL,
        ),
        actor="development-seed",
    )
    observations.add_vitals(
        encounter.id,
        VitalSignsCreate(
            heart_rate=86,
            systolic_bp=132,
            diastolic_bp=84,
            spo2=98,
            respiratory_rate=17,
            temperature=36.8,
            measured_at=HISTORICAL_ENCOUNTER_START,
            source=ObservationSource.MANUAL,
        ),
        actor="development-seed",
    )
    observations.add_lab(
        encounter.id,
        LabResultCreate(
            test_name="troponin",
            value=0.01,
            unit="ng/mL",
            collected_at=HISTORICAL_ENCOUNTER_START,
            source=ObservationSource.EHR,
        ),
        actor="development-seed",
    )


def _seed_current_encounter(session, patients: PatientService, patient_id: str, case: dict):
    existing = _encounter_with_marker(
        patients, patient_id, (CURRENT_MARKER, LEGACY_CURRENT_MARKER)
    )
    if existing is not None and _case_matches(session, existing, case):
        return existing, False
    if existing is None:
        encounter = EncounterService(session).create(
            patient_id,
            EncounterCreate(
                encounter_type="emergency",
                chief_complaint=case["chief_complaint"],
                clinician_notes=_current_notes(case),
                started_at=case["started_at"],
            ),
            actor="development-seed",
        )
    else:
        encounter = existing
        encounter.encounter_type = "emergency"
        encounter.chief_complaint = case["chief_complaint"]
        encounter.clinician_notes = _current_notes(case)
        encounter.status = EncounterStatus.ACTIVE
        encounter.started_at = case["started_at"]
        encounter.completed_at = None
        session.execute(delete(Symptom).where(Symptom.encounter_id == encounter.id))
        session.execute(delete(VitalSigns).where(VitalSigns.encounter_id == encounter.id))
        session.execute(delete(LabResult).where(LabResult.encounter_id == encounter.id))
        session.commit()

    observations = ObservationService(session)
    for symptom in case["symptoms"]:
        observations.add_symptom(
            encounter.id,
            SymptomCreate(
                **symptom,
                source=ObservationSource.MANUAL,
            ),
            actor="development-seed",
        )
    for vital_signs in case["vitals"]:
        observations.add_vitals(
            encounter.id,
            VitalSignsCreate(
                **vital_signs,
                source=ObservationSource.MANUAL,
            ),
            actor="development-seed",
        )
    for lab_result in case["labs"]:
        observations.add_lab(
            encounter.id,
            LabResultCreate(
                **lab_result,
                source=ObservationSource.MANUAL,
            ),
            actor="development-seed",
        )
    session.expire(encounter, ["symptoms", "vital_signs", "lab_results"])
    return encounter, True


def _ensure_queue_entries(
    session, patient_encounters: list[tuple[str, str, bool]]
) -> None:
    unavailable_provider = GeminiProvider(api_key="", model="gemini-3.6-flash")
    graph = build_clinical_graph(
        session,
        clinical_reasoning_agent=ClinicalReasoningAgent(
            session, provider=unavailable_provider
        ),
    )
    for patient_id, encounter_id, data_changed in patient_encounters:
        existing = session.scalar(
            select(QueueEntry).where(QueueEntry.encounter_id == encounter_id)
        )
        if existing is None or data_changed:
            result = graph.invoke(
                create_initial_clinical_state(patient_id, encounter_id),
                config={"recursion_limit": 32},
            )
            if result.get("workflow_status") != "COMPLETED":
                raise RuntimeError(f"Demo workflow did not complete for {encounter_id}")
            priority = result.get("priority") or {}
            if existing is not None and data_changed and not priority.get("queue_entry_id"):
                session.delete(existing)
                session.commit()


def seed_development_data() -> tuple[str, str]:
    with SessionLocal() as session:
        patients = PatientService(session)
        seeded = [_patient_for_case(session, patients, case) for case in DEMO_CASES]
        _seed_historical_encounter(session, patients, seeded[0].id)
        encounter_results = [
            _seed_current_encounter(session, patients, patient.id, case)
            for patient, case in zip(seeded, DEMO_CASES, strict=True)
        ]
        _ensure_queue_entries(
            session,
            [
                (patient.id, encounter.id, data_changed)
                for patient, (encounter, data_changed) in zip(
                    seeded, encounter_results, strict=True
                )
            ],
        )
        return seeded[0].id, seeded[1].id


if __name__ == "__main__":
    seeded_patient_a, seeded_patient_b = seed_development_data()
    print(f"Seeded deterministic synthetic demo (DEMO-001 primary): {seeded_patient_a}")
    print(f"Seeded additional demo patients (DEMO-002 through DEMO-010): {seeded_patient_b}")

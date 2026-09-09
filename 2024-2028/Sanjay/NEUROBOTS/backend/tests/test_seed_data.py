from app.core.enums import ObservationSource
from app.schemas.clinical import LabResultCreate, SymptomCreate, VitalSignsCreate
from app.seed import (
    DEMO_CASES,
    _patient_for_case,
    _seed_current_encounter,
)
from app.services.observations import ObservationService
from app.services.patients import PatientService


def test_demo_cases_are_diverse_and_chronologically_consistent() -> None:
    assert len(DEMO_CASES) == 10
    assert [case["external_patient_id"] for case in DEMO_CASES] == [
        f"DEMO-{index:03d}" for index in range(1, 11)
    ]
    assert len({case["scenario"] for case in DEMO_CASES}) == 10

    for case in DEMO_CASES:
        for symptom in case["symptoms"]:
            validated = SymptomCreate(**symptom)
            assert validated.onset is not None
            assert validated.onset <= case["started_at"]
        for vital_signs in case["vitals"]:
            validated = VitalSignsCreate(**vital_signs)
            assert validated.measured_at >= case["started_at"]
            assert 40 <= validated.heart_rate <= 180
            assert 80 <= validated.systolic_bp <= 240
            assert 40 <= validated.diastolic_bp <= 140
            assert 80 <= validated.spo2 <= 100
            assert 10 <= validated.respiratory_rate <= 40
            assert 35 <= validated.temperature <= 41
        for lab_result in case["labs"]:
            validated = LabResultCreate(**lab_result)
            assert validated.collected_at >= case["started_at"]


def test_seed_repairs_noncanonical_demo_observations(db_session) -> None:
    case = DEMO_CASES[2]
    patients = PatientService(db_session)
    patient = _patient_for_case(db_session, patients, case)
    encounter, changed = _seed_current_encounter(
        db_session, patients, patient.id, case
    )
    assert changed is True

    observations = ObservationService(db_session)
    observations.add_symptom(
        encounter.id,
        SymptomCreate(
            name="invalid sample symptom",
            severity=2,
            source=ObservationSource.MANUAL,
        ),
    )
    observations.add_vitals(
        encounter.id,
        VitalSignsCreate(
            heart_rate=18,
            systolic_bp=7,
            diastolic_bp=13,
            spo2=9,
            respiratory_rate=9,
            temperature=24,
            source=ObservationSource.MANUAL,
        ),
    )
    observations.add_lab(
        encounter.id,
        LabResultCreate(
            test_name="45",
            value=45,
            source=ObservationSource.MANUAL,
        ),
    )

    repaired, changed = _seed_current_encounter(
        db_session, patients, patient.id, case
    )
    assert repaired.id == encounter.id
    assert changed is True
    assert len(observations.list_symptoms(encounter.id)) == len(case["symptoms"])
    assert len(observations.list_vitals(encounter.id)) == len(case["vitals"])
    assert len(observations.list_labs(encounter.id)) == len(case["labs"])

    _, changed = _seed_current_encounter(db_session, patients, patient.id, case)
    assert changed is False

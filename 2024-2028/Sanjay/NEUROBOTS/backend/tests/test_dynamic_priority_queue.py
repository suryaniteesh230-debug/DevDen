from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.clinical_agents import PriorityAgent, SafetyAgent, XaiAgent
from app.core.enums import QueueStatus
from app.db.models import (
    AuditEvent,
    ClinicalEncounter,
    Patient,
    QueueEntry,
    QueuePriorityCalculation,
    TriageAssessment,
)
from app.priority.deterioration import detect_deterioration
from app.priority.policy import DynamicPriorityPolicy
from app.services.dynamic_queue import DynamicQueueService
from app.workflows.clinical_state import create_initial_clinical_state
from tests.conftest import ApiClient


NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def _persist_context(
    session: Session,
    suffix: str,
    *,
    started_at: datetime | None = None,
    severity_level: str = "PROTOTYPE_ESI_2",
    prototype_esi_level: int | None = 2,
) -> tuple[Patient, ClinicalEncounter, dict]:
    patient = Patient(
        external_patient_id=f"QUEUE-{suffix}",
        first_name="Queue",
        last_name=suffix,
        date_of_birth=date(1970, 1, 1),
        gender="unspecified",
    )
    encounter = ClinicalEncounter(
        patient=patient,
        encounter_type="emergency",
        chief_complaint="Queue policy test",
        started_at=started_at or NOW,
    )
    assessment = TriageAssessment(
        encounter=encounter,
        policy_name="NEUROBOTS Prototype ESI Subset",
        policy_version="prototype-esi-subset-1.0.0",
        severity_level=severity_level,
        provisional=True,
        completeness_metadata={},
        confidence_metadata={},
        rule_hits=[],
        missing_information=["clinician_high_risk_assessment"],
        input_snapshot={},
        evaluation_latency_ms=0.01,
    )
    session.add_all([patient, encounter, assessment])
    session.commit()
    triage = {
        "status": "SUCCESS",
        "assessment_id": assessment.id,
        "policy_name": assessment.policy_name,
        "policy_version": assessment.policy_version,
        "severity_level": severity_level,
        "prototype_esi_level": prototype_esi_level,
        "provisional": True,
        "missing_information": assessment.missing_information,
    }
    return patient, encounter, triage


def _cardiac(probability: float, predicted_class: int = 1) -> dict:
    return {
        "status": "SUCCESS",
        "predicted_class": predicted_class,
        "probability": probability,
        "model_version": "cardiac-risk-rf-1.0.0",
        "prediction_id": None,
    }


def _vitals(*rows: tuple[str, str, float, float, float, float]) -> list[dict]:
    return [
        {
            "id": identifier,
            "measured_at": measured_at,
            "heart_rate": heart_rate,
            "systolic_bp": systolic_bp,
            "spo2": spo2,
            "respiratory_rate": respiratory_rate,
        }
        for identifier, measured_at, heart_rate, systolic_bp, spo2, respiratory_rate in rows
    ]


def _recalculate(
    service: DynamicQueueService,
    patient: Patient,
    encounter: ClinicalEncounter,
    triage: dict,
    *,
    cardiac: dict | None = None,
    vitals: list[dict] | None = None,
    waiting_since: datetime | None = None,
    now: datetime = NOW,
) -> dict:
    return service.recalculate(
        encounter_id=encounter.id,
        patient_id=patient.id,
        triage=triage,
        cardiac_risk=cardiac,
        vital_history=vitals or [],
        waiting_since=waiting_since or encounter.started_at,
        now=now,
    )


def test_priority_policy_loads_with_independent_version_and_rules() -> None:
    metadata = DynamicPriorityPolicy().metadata

    assert metadata["policy_name"] == "NEUROBOTS Dynamic Priority Policy"
    assert metadata["policy_version"] == "dynamic-priority-1.0.0"
    assert [item["id"] for item in metadata["rule_definitions"]] == [
        "PRIORITY-001",
        "PRIORITY-002",
        "PRIORITY-003",
        "PRIORITY-004",
        "PRIORITY-005",
    ]
    assert metadata["deterioration"]["policy_version"] == "vital-deterioration-1.0.0"


def test_new_registration_is_visible_as_pending_intake(
    client: ApiClient, patient: dict
) -> None:
    response = client.get("/api/queue/pending")

    assert response.status_code == 200
    [pending] = response.json()
    assert pending["id"] == f"pending:{patient['id']}"
    assert pending["patient_id"] == patient["id"]
    assert pending["encounter_id"] is None
    assert pending["patient_display"] == {
        "display_name": "Mira Patel",
        "age_years": datetime.now(timezone.utc).year - 1978,
        "chief_complaint": "Chief complaint not recorded",
    }
    assert pending["intake_stage"] == "REGISTRATION"
    assert pending["waiting_duration_minutes"] >= 0


def test_pending_intake_moves_to_triage_after_encounter_creation(
    client: ApiClient, patient: dict, encounter: dict
) -> None:
    response = client.get("/api/queue/pending")

    assert response.status_code == 200
    [pending] = response.json()
    assert pending["id"] == f"pending:{encounter['id']}"
    assert pending["patient_id"] == patient["id"]
    assert pending["encounter_id"] == encounter["id"]
    assert pending["patient_display"]["chief_complaint"] == "Chest pain"
    assert pending["intake_stage"] == "TRIAGE"


def test_ranked_encounter_is_not_duplicated_in_pending_intake(db_session: Session) -> None:
    patient, encounter, triage = _persist_context(db_session, "PENDING-TO-RANKED")
    service = DynamicQueueService(db_session)

    assert service.list_pending_intake() == [(patient, encounter)]
    _recalculate(service, patient, encounter, triage)

    assert service.list_pending_intake() == []


def test_triage_is_required_and_undetermined_triage_does_not_create_queue_entry(
    db_session: Session,
) -> None:
    patient, encounter, triage = _persist_context(
        db_session,
        "NO-TRIAGE",
        severity_level="UNDETERMINED",
        prototype_esi_level=None,
    )

    result = _recalculate(DynamicQueueService(db_session), patient, encounter, triage)

    assert result["status"] == "PENDING_TRIAGE"
    assert result["priority_score"] is None
    assert db_session.scalar(select(QueueEntry)) is None


def test_queue_entry_and_append_only_calculation_persist_with_audit(
    db_session: Session,
) -> None:
    patient, encounter, triage = _persist_context(db_session, "PERSIST")
    service = DynamicQueueService(db_session)

    result = _recalculate(service, patient, encounter, triage)

    entry = db_session.get(QueueEntry, result["queue_entry_id"])
    calculations = list(db_session.scalars(select(QueuePriorityCalculation)).all())
    events = list(db_session.scalars(select(AuditEvent)).all())
    assert entry is not None
    assert entry.triage_assessment_id == triage["assessment_id"]
    assert len(calculations) == 1
    assert calculations[0].rule_trace == result["rule_trace"]
    assert events[-1].event_type == "QUEUE_ENTRY_CREATED"


def test_cardiac_risk_is_fixed_support_not_probability_copy() -> None:
    policy = DynamicPriorityPolicy()
    _, _, triage = _standalone_triage()
    low = policy.calculate(
        triage=triage,
        cardiac_risk=_cardiac(0.79),
        vital_history=[],
        waiting_since=NOW,
        now=NOW,
    )
    high = policy.calculate(
        triage=triage,
        cardiac_risk=_cardiac(0.99),
        vital_history=[],
        waiting_since=NOW,
        now=NOW,
    )

    assert high["priority_score"] - low["priority_score"] == 5
    assert high["priority_score"] != high["input_snapshot"]["cardiac_risk"]["probability"]
    rule = next(item for item in high["rule_trace"] if item["id"] == "PRIORITY-003")
    assert rule["contribution"] == 5


def _standalone_triage(
    severity: str = "PROTOTYPE_ESI_2", prototype_esi_level: int | None = 2
) -> tuple[None, None, dict]:
    return None, None, {
        "status": "SUCCESS",
        "assessment_id": "assessment-1",
        "policy_name": "NEUROBOTS Prototype ESI Subset",
        "policy_version": "prototype-esi-subset-1.0.0",
        "severity_level": severity,
        "prototype_esi_level": prototype_esi_level,
        "provisional": True,
        "missing_information": ["full_esi_inputs"],
    }


def test_priority_band_is_not_an_esi_level() -> None:
    _, _, triage = _standalone_triage()
    result = DynamicPriorityPolicy().calculate(
        triage=triage,
        cardiac_risk=None,
        vital_history=[],
        waiting_since=NOW,
        now=NOW,
    )

    assert result["prototype_esi_level"] == 2
    assert result["priority_band"] == "VERY_HIGH"
    assert result["priority_band"] != result["prototype_esi_level"]


def test_waiting_time_adjustment_is_capped_and_does_not_reduce_provisional_priority() -> None:
    _, _, triage = _standalone_triage("ROUTINE", None)
    result = DynamicPriorityPolicy().calculate(
        triage=triage,
        cardiac_risk=None,
        vital_history=[],
        waiting_since=NOW - timedelta(hours=10),
        now=NOW,
    )

    waiting_rule = next(item for item in result["rule_trace"] if item["id"] == "PRIORITY-004")
    provisional_rule = next(
        item for item in result["rule_trace"] if item["id"] == "PRIORITY-005"
    )
    assert waiting_rule["contribution"] == 5
    assert provisional_rule["contribution"] == 0
    assert result["priority_score"] == 25


def test_waiting_alone_cannot_overwhelm_critical_severity() -> None:
    policy = DynamicPriorityPolicy()
    _, _, routine = _standalone_triage("ROUTINE", None)
    _, _, critical = _standalone_triage("CRITICAL", None)
    waited = policy.calculate(
        triage=routine,
        cardiac_risk=None,
        vital_history=[],
        waiting_since=NOW - timedelta(days=7),
        now=NOW,
    )
    new_critical = policy.calculate(
        triage=critical,
        cardiac_risk=None,
        vital_history=[],
        waiting_since=NOW,
        now=NOW,
    )

    assert waited["priority_score"] < new_critical["priority_score"]


def test_one_vital_reading_reports_unknown_without_fabricating_deterioration() -> None:
    result = detect_deterioration(
        _vitals(("v1", "2026-08-08T11:50:00Z", 80, 125, 98, 16))
    )

    assert result["status"] == "UNKNOWN"
    assert result["signals"] == []


def test_repeated_vitals_use_chronological_order_and_detect_supported_changes() -> None:
    readings = _vitals(
        ("latest", "2026-08-08T11:55:00Z", 105, 100, 94, 24),
        ("old", "2026-08-08T11:30:00Z", 75, 130, 98, 16),
        ("middle", "2026-08-08T11:40:00Z", 80, 125, 97, 17),
    )

    result = detect_deterioration(readings)

    assert result["status"] == "DETECTED"
    assert result["previous_vital_id"] == "middle"
    assert result["latest_vital_id"] == "latest"
    assert {item["id"] for item in result["signals"]} == {
        "HEART_RATE_RISE",
        "SYSTOLIC_BP_DROP",
        "SPO2_DROP",
        "RESPIRATORY_RATE_RISE",
    }


def test_deterioration_increases_priority_with_stable_rule_contribution() -> None:
    _, _, triage = _standalone_triage()
    stable_vitals = _vitals(
        ("v1", "2026-08-08T11:40:00Z", 80, 125, 98, 16),
        ("v2", "2026-08-08T11:50:00Z", 82, 124, 98, 17),
    )
    worse_vitals = _vitals(
        ("v1", "2026-08-08T11:40:00Z", 80, 125, 98, 16),
        ("v2", "2026-08-08T11:50:00Z", 105, 100, 94, 23),
    )
    policy = DynamicPriorityPolicy()
    stable = policy.calculate(
        triage=triage, cardiac_risk=None, vital_history=stable_vitals, waiting_since=NOW, now=NOW
    )
    worse = policy.calculate(
        triage=triage, cardiac_risk=None, vital_history=worse_vitals, waiting_since=NOW, now=NOW
    )

    assert worse["priority_score"] - stable["priority_score"] == 15
    assert worse["priority_band"] == "CRITICAL"


def test_multiple_patients_sort_and_tie_break_deterministically(db_session: Session) -> None:
    service = DynamicQueueService(db_session)
    routine_patient, routine_encounter, routine_triage = _persist_context(
        db_session, "ROUTINE", started_at=NOW - timedelta(hours=5), severity_level="ROUTINE", prototype_esi_level=None
    )
    first_patient, first_encounter, first_triage = _persist_context(
        db_session, "FIRST", started_at=NOW - timedelta(minutes=30)
    )
    second_patient, second_encounter, second_triage = _persist_context(
        db_session, "SECOND", started_at=NOW - timedelta(minutes=30)
    )
    _recalculate(service, routine_patient, routine_encounter, routine_triage)
    first = _recalculate(service, first_patient, first_encounter, first_triage)
    second = _recalculate(service, second_patient, second_encounter, second_triage)

    ordered = service.list()
    assert [item.id for item in ordered] == [
        first["queue_entry_id"],
        second["queue_entry_id"],
        service.entries.get_for_encounter(routine_encounter.id).id,
    ]
    assert [service.rank(item.id) for item in ordered] == [1, 2, 3]


def test_recalculation_updates_current_entry_and_preserves_history_and_audit(
    db_session: Session,
) -> None:
    patient, encounter, triage = _persist_context(db_session, "RECALC")
    service = DynamicQueueService(db_session)
    first = _recalculate(
        service,
        patient,
        encounter,
        triage,
        vitals=_vitals(("v1", "2026-08-08T11:50:00Z", 80, 125, 98, 16)),
    )
    second = _recalculate(
        service,
        patient,
        encounter,
        triage,
        vitals=_vitals(
            ("v1", "2026-08-08T11:50:00Z", 80, 125, 98, 16),
            ("v2", "2026-08-08T11:55:00Z", 105, 100, 94, 23),
        ),
    )

    assert first["queue_entry_id"] == second["queue_entry_id"]
    assert second["priority_score"] > first["priority_score"]
    calculations = list(db_session.scalars(select(QueuePriorityCalculation)).all())
    assert [item.deterioration_status for item in calculations] == ["UNKNOWN", "DETECTED"]
    events = list(
        db_session.scalars(
            select(AuditEvent).where(
                AuditEvent.event_type.in_(
                    ["QUEUE_ENTRY_CREATED", "QUEUE_PRIORITY_RECALCULATED"]
                )
            )
        ).all()
    )
    assert [item.event_type for item in events] == [
        "QUEUE_ENTRY_CREATED",
        "QUEUE_PRIORITY_RECALCULATED",
    ]


def test_workflow_reassessment_creates_new_triage_and_reprioritizes_from_new_vital(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter_response = client.post(
        f"/api/patients/{patient['id']}/encounters",
        json={
            "encounter_type": "emergency",
            "chief_complaint": "Chest pain and shortness of breath",
            "started_at": "2026-08-08T11:00:00Z",
        },
    )
    encounter = encounter_response.json()
    for name in ("chest pain", "shortness of breath"):
        assert client.post(
            f"/api/encounters/{encounter['id']}/symptoms",
            json={"name": name, "severity": 7},
        ).status_code == 201
    for lab in (
        {"test_name": "blood sugar", "value": 100},
        {"test_name": "CK-MB", "value": 0.5},
        {"test_name": "troponin", "value": 0.001},
    ):
        assert client.post(
            f"/api/encounters/{encounter['id']}/labs", json=lab
        ).status_code == 201
    first_vital = client.post(
        f"/api/encounters/{encounter['id']}/vitals",
        json={
            "heart_rate": 80,
            "systolic_bp": 125,
            "diastolic_bp": 78,
            "spo2": 98,
            "respiratory_rate": 16,
            "measured_at": "2026-08-08T11:05:00Z",
        },
    ).json()
    first = client.post(f"/api/encounters/{encounter['id']}/workflow").json()
    second_vital = client.post(
        f"/api/encounters/{encounter['id']}/vitals",
        json={
            "heart_rate": 105,
            "systolic_bp": 100,
            "diastolic_bp": 70,
            "spo2": 94,
            "respiratory_rate": 23,
            "measured_at": "2026-08-08T11:15:00Z",
        },
    ).json()
    second = client.post(f"/api/encounters/{encounter['id']}/workflow").json()

    assert first["triage"]["assessment_id"] != second["triage"]["assessment_id"]
    assert first["priority"]["queue_entry_id"] == second["priority"]["queue_entry_id"]
    assert first["priority"]["deterioration_status"] == "UNKNOWN"
    assert second["priority"]["deterioration_status"] == "DETECTED"
    assert second["priority"]["priority_score"] > first["priority"]["priority_score"]
    assert first["priority"]["deterioration"]["latest_vital_id"] == first_vital["id"]
    assert second["priority"]["deterioration"]["latest_vital_id"] == second_vital["id"]
    db_session.expire_all()
    calculations = list(
        db_session.scalars(
            select(QueuePriorityCalculation).where(
                QueuePriorityCalculation.queue_entry_id
                == second["priority"]["queue_entry_id"]
            )
        ).all()
    )
    assert len(calculations) == 2


def test_queue_api_returns_ordered_minimal_contract(db_session: Session, client: ApiClient) -> None:
    service = DynamicQueueService(db_session)
    for suffix, severity, minutes in (
        ("LOW", "ROUTINE", 180),
        ("HIGH", "PROTOTYPE_ESI_2", 5),
    ):
        patient, encounter, triage = _persist_context(
            db_session,
            suffix,
            started_at=NOW - timedelta(minutes=minutes),
            severity_level=severity,
            prototype_esi_level=2 if severity == "PROTOTYPE_ESI_2" else None,
        )
        _recalculate(service, patient, encounter, triage)

    response = client.get("/api/queue")

    assert response.status_code == 200
    body = response.json()
    assert [item["rank"] for item in body] == [1, 2]
    assert body[0]["priority_score"] > body[1]["priority_score"]
    assert "first_name" not in body[0]
    assert "input_snapshot" not in body[0]
    assert body[0]["prototype_esi_level"] == 2


def test_queue_status_api_updates_and_terminal_entries_leave_waiting_queue(
    db_session: Session, client: ApiClient
) -> None:
    patient, encounter, triage = _persist_context(db_session, "STATUS")
    result = _recalculate(DynamicQueueService(db_session), patient, encounter, triage)

    completed = client.patch(
        f"/api/queue/{result['queue_entry_id']}",
        json={"queue_status": "COMPLETED"},
    )

    assert completed.status_code == 200
    assert completed.json()["queue_status"] == "COMPLETED"
    assert client.get("/api/queue").json() == []
    completed_list = client.get("/api/queue", params={"status": "COMPLETED"}).json()
    assert [item["id"] for item in completed_list] == [result["queue_entry_id"]]
    event = db_session.scalar(
        select(AuditEvent).where(AuditEvent.event_type == "QUEUE_STATUS_CHANGED")
    )
    assert event is not None


def test_removed_entries_leave_queue_and_invalid_status_is_rejected(
    db_session: Session, client: ApiClient
) -> None:
    patient, encounter, triage = _persist_context(db_session, "REMOVED")
    result = _recalculate(DynamicQueueService(db_session), patient, encounter, triage)

    invalid = client.patch(
        f"/api/queue/{result['queue_entry_id']}",
        json={"queue_status": "URGENT"},
    )
    removed = client.patch(
        f"/api/queue/{result['queue_entry_id']}",
        json={"queue_status": "REMOVED"},
    )

    assert invalid.status_code == 422
    assert removed.status_code == 200
    assert client.get("/api/queue").json() == []


def test_priority_agent_populates_state_and_missing_triage_is_safe(db_session: Session) -> None:
    patient, encounter, triage = _persist_context(db_session, "AGENT")
    state = create_initial_clinical_state(patient.id, encounter.id)
    state["encounter"] = {"id": encounter.id, "started_at": encounter.started_at.isoformat()}
    state["triage"] = triage
    state["vitals"] = _vitals(("v1", "2026-08-08T11:50:00Z", 80, 125, 98, 16))
    state["current_vitals"] = state["vitals"][0]

    success = PriorityAgent(db_session)(state)
    empty_state = create_initial_clinical_state(patient.id, encounter.id)
    pending = PriorityAgent(db_session)(empty_state)

    assert success["priority"]["status"] == "SUCCESS"
    assert success["priority"]["queue_entry_id"]
    assert pending["priority"]["status"] == "PENDING_TRIAGE"


def test_safety_validates_priority_metadata_provisional_state_and_staleness() -> None:
    state = create_initial_clinical_state("patient-1", "encounter-1")
    _, _, triage = _standalone_triage()
    state["triage"] = triage
    state["current_vitals"] = {"id": "new-vital"}
    state["priority"] = {
        "status": "SUCCESS",
        "policy_name": None,
        "policy_version": None,
        "priority_score": 150,
        "priority_band": "ESI_2",
        "triage_assessment_id": "old-assessment",
        "provisional": False,
        "deterioration": {"latest_vital_id": "old-vital"},
    }

    findings = SafetyAgent()(state)["safety_findings"]["findings"]
    types = {item["type"] for item in findings}

    assert {
        "INCONSISTENT_PRIORITY_METADATA",
        "INVALID_PRIORITY_VALUE",
        "INCONSISTENT_PRIORITY_PROVISIONAL_FLAG",
        "STALE_PRIORITY",
    } <= types


def test_xai_exposes_priority_as_a_fourth_separate_channel(db_session: Session) -> None:
    state = create_initial_clinical_state("patient-1", "encounter-1")
    state["triage"] = {"policy_name": "triage", "policy_version": "1", "rule_hits": []}
    state["priority"] = {
        "status": "SUCCESS",
        "policy_name": "NEUROBOTS Dynamic Priority Policy",
        "policy_version": "dynamic-priority-1.0.0",
        "priority_score": 80,
        "priority_band": "VERY_HIGH",
        "reason_codes": ["PRIORITY-001", "PRIORITY-005"],
        "deterioration_status": "UNKNOWN",
        "provisional": True,
        "rule_trace": [{"id": "PRIORITY-001"}],
    }

    explanation = XaiAgent(db_session)(state)["explanation"]

    assert explanation["model_contributions"] is None
    assert explanation["triage_rule_trace"] is not None
    assert explanation["clinical_reasoning_evidence"] is not None
    assert explanation["priority_rule_trace"]["policy_version"] == "dynamic-priority-1.0.0"
    assert explanation["priority_rule_trace"]["rules"] == [{"id": "PRIORITY-001"}]

from __future__ import annotations

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.clinical_agents import PriorityAgent, SafetyAgent
from app.db.models import TriageAssessment
from app.triage.policy import EmergencyTriageTool
from app.workflows.clinical_state import create_initial_clinical_state
from tests.conftest import ApiClient


def _fused_context() -> dict:
    return {
        "patient": {
            "id": "patient-1",
            "date_of_birth": "1978-04-18",
            "gender": "female",
        },
        "encounter": {
            "id": "encounter-1",
            "started_at": "2026-08-07T08:00:00Z",
        },
        "symptoms": [
            {
                "name": "chest pain",
                "present": True,
                "severity": 8,
                "duration": "30 minutes",
                "onset": "2026-08-07T07:30:00Z",
            },
            {"name": "shortness of breath", "present": True, "severity": 7},
        ],
        "vitals": {
            "latest": {
                "id": "vitals-1",
                "heart_rate": 108,
                "systolic_bp": 148,
                "diastolic_bp": 90,
                "spo2": 95,
                "respiratory_rate": 22,
                "temperature": 37.1,
            }
        },
        "previous_encounters": [],
    }


def _cardiac(probability: float = 0.91) -> dict:
    return {
        "status": "SUCCESS",
        "predicted_class": 1,
        "probability": probability,
        "model_version": "cardiac-risk-rf-1.0.0",
    }


def _create_encounter(client: ApiClient, patient_id: str) -> dict:
    response = client.post(
        f"/api/patients/{patient_id}/encounters",
        json={
            "encounter_type": "emergency",
            "chief_complaint": "Chest pain",
            "started_at": "2026-08-07T08:00:00Z",
        },
    )
    assert response.status_code == 201
    return response.json()


def _add_model_inputs(client: ApiClient, encounter_id: str) -> None:
    assert client.post(
        f"/api/encounters/{encounter_id}/symptoms",
        json={"name": "chest pain", "severity": 6, "duration": "20 minutes"},
    ).status_code == 201
    for lab in (
        {"test_name": "blood sugar", "value": 146, "unit": "mg/dL"},
        {"test_name": "CK-MB", "value": 8.4, "unit": "ng/mL"},
        {"test_name": "troponin", "value": 0.18, "unit": "ng/mL"},
    ):
        assert client.post(
            f"/api/encounters/{encounter_id}/labs", json=lab
        ).status_code == 201


def test_policy_loads_with_explicit_independent_version_and_limitations() -> None:
    tool = EmergencyTriageTool()

    assert tool.policy_version == "prototype-esi-subset-1.0.0"
    assert tool.metadata["policy_name"] == "NEUROBOTS Prototype ESI Subset"
    assert tool.metadata["reference_sources"]
    assert any("not clinically validated" in item for item in tool.metadata["limitations"])


def test_valid_fused_context_produces_auditable_provisional_assessment() -> None:
    result = EmergencyTriageTool().assess(_fused_context(), _cardiac())

    assert result["status"] == "SUCCESS"
    assert result["severity_level"] == "PROTOTYPE_ESI_2"
    assert result["prototype_esi_level"] == 2
    assert result["esi"] is None
    assert result["assigned_priority"] is None
    assert result["provisional"] is True
    assert result["evaluation_latency_ms"] >= 0
    assert [item["id"] for item in result["rule_hits"]] == [
        "TRIAGE-001",
        "TRIAGE-002",
        "TRIAGE-003",
        "TRIAGE-004",
        "TRIAGE-005",
    ]
    assert all(
        {"id", "version", "description", "inputs_used", "triggered", "effect"}
        <= item.keys()
        for item in result["rule_hits"]
    )


def test_missing_inputs_are_surfaced_and_never_fabricated() -> None:
    result = EmergencyTriageTool().assess({}, None)

    assert result["severity_level"] == "UNDETERMINED"
    assert result["prototype_esi_level"] is None
    assert result["input_snapshot"]["latest_vitals"] == {}
    assert result["input_snapshot"]["symptoms"] == []
    assert result["confidence"]["numeric_confidence"] is None
    assert "spo2" in result["missing_information"]
    assert "consciousness_level" in result["missing_information"]
    assert result["completeness"]["full_esi_inputs_complete"] is False


def test_cardiac_probability_is_supporting_only_and_cannot_become_severity() -> None:
    context = _fused_context()
    context["symptoms"] = []
    context["vitals"]["latest"].update(
        heart_rate=80, respiratory_rate=16, spo2=98
    )

    high = EmergencyTriageTool().assess(context, _cardiac(0.99))
    low = EmergencyTriageTool().assess(context, _cardiac(0.10))

    assert high["severity_level"] == low["severity_level"] == "UNDETERMINED"
    assert high["rationale"]["cardiac_risk_used_for_level"] is False
    high_cardiac_rule = next(
        item for item in high["rule_hits"] if item["id"] == "TRIAGE-004"
    )
    assert high_cardiac_rule["triggered"] is True
    assert high_cardiac_rule["effect"] == "SUPPORTING_SIGNAL_ONLY"


def test_workflow_persists_append_only_reassessment_from_latest_vitals(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"])
    _add_model_inputs(client, encounter["id"])
    first_vitals = client.post(
        f"/api/encounters/{encounter['id']}/vitals",
        json={
            "heart_rate": 80,
            "systolic_bp": 130,
            "diastolic_bp": 80,
            "spo2": 98,
            "respiratory_rate": 16,
            "measured_at": "2026-08-07T08:05:00Z",
        },
    ).json()

    first = client.post(f"/api/encounters/{encounter['id']}/workflow").json()
    immutable_first = deepcopy(first["triage"])
    second_vitals = client.post(
        f"/api/encounters/{encounter['id']}/vitals",
        json={
            "heart_rate": 108,
            "systolic_bp": 148,
            "diastolic_bp": 90,
            "spo2": 95,
            "respiratory_rate": 22,
            "measured_at": "2026-08-07T08:10:00Z",
        },
    ).json()
    second = client.post(f"/api/encounters/{encounter['id']}/workflow").json()

    assert first["cardiac_risk"]["status"] == second["cardiac_risk"]["status"] == "SUCCESS"
    assert first["triage"]["assessment_id"] != second["triage"]["assessment_id"]
    assert first["triage"]["severity_level"] == "UNDETERMINED"
    assert second["triage"]["severity_level"] == "PROTOTYPE_ESI_2"
    assert first["triage"] == immutable_first
    assert first["triage"]["input_snapshot"]["latest_vitals"]["id"] == first_vitals["id"]
    assert second["triage"]["input_snapshot"]["latest_vitals"]["id"] == second_vitals["id"]

    db_session.expire_all()
    assessments = list(
        db_session.scalars(
            select(TriageAssessment)
            .where(TriageAssessment.encounter_id == encounter["id"])
            .order_by(TriageAssessment.created_at, TriageAssessment.id)
        ).all()
    )
    assert len(assessments) == 2
    assert [item.severity_level for item in assessments] == [
        "UNDETERMINED",
        "PROTOTYPE_ESI_2",
    ]
    assert assessments[0].input_snapshot["latest_vitals"]["id"] == first_vitals["id"]


def test_triage_degrades_gracefully_when_cardiac_risk_is_unavailable(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"])
    for symptom in ("chest pain", "shortness of breath"):
        assert client.post(
            f"/api/encounters/{encounter['id']}/symptoms", json={"name": symptom}
        ).status_code == 201
    assert client.post(
        f"/api/encounters/{encounter['id']}/vitals",
        json={"heart_rate": 108, "spo2": 95, "respiratory_rate": 22},
    ).status_code == 201

    result = client.post(f"/api/encounters/{encounter['id']}/workflow").json()

    assert result["cardiac_risk"]["status"] == "INCOMPLETE_INPUT"
    assert result["triage"]["status"] == "SUCCESS"
    assert result["triage"]["severity_level"] == "PROTOTYPE_ESI_2"
    assert result["triage"]["assessment_id"]
    assert result["explanation"]["model_contributions"] is None
    assert result["explanation"]["triage_rule_trace"]["rules"]
    assert next(
        item for item in result["agent_trace"] if item["agent"] == "triage_risk"
    )["status"] == "PARTIAL"
    db_session.expire_all()
    assert len(list(db_session.scalars(select(TriageAssessment)).all())) == 1


def test_xai_separates_model_contributions_from_triage_rule_trace(
    client: ApiClient, patient: dict
) -> None:
    encounter = _create_encounter(client, patient["id"])
    _add_model_inputs(client, encounter["id"])
    assert client.post(
        f"/api/encounters/{encounter['id']}/vitals",
        json={"heart_rate": 108, "systolic_bp": 148, "diastolic_bp": 90},
    ).status_code == 201

    result = client.post(f"/api/encounters/{encounter['id']}/workflow").json()
    explanation = result["explanation"]

    assert explanation["model_contributions"]["method"] == "TreeSHAP"
    assert explanation["model_contributions"]["feature_contributions"]
    assert explanation["triage_rule_trace"]["policy_version"] == (
        "prototype-esi-subset-1.0.0"
    )
    assert explanation["triage_rule_trace"]["rules"]
    assert "feature_contributions" not in explanation["triage_rule_trace"]


def test_safety_flags_provisional_missing_and_inconsistent_triage() -> None:
    state = create_initial_clinical_state("patient-1", "encounter-1")
    state["triage"] = {
        "status": "SUCCESS",
        "severity_level": "PROTOTYPE_ESI_2",
        "provisional": True,
        "missing_information": ["consciousness_level"],
    }

    updates = SafetyAgent()(state)
    types = {item["type"] for item in updates["safety_findings"]["findings"]}

    assert "PROVISIONAL_TRIAGE" in types
    assert "TRIAGE_MISSING_INFORMATION" in types
    assert "INCONSISTENT_TRIAGE_METADATA" in types


def test_priority_agent_requires_persisted_usable_triage(db_session: Session) -> None:
    state = create_initial_clinical_state("patient-1", "encounter-1")
    state["triage"] = {
        "status": "SUCCESS",
        "severity_level": "PROTOTYPE_ESI_2",
        "prototype_esi_level": 2,
        "assigned_priority": None,
    }

    updates = PriorityAgent(db_session)(state)

    assert updates["priority"]["status"] == "PENDING_TRIAGE"
    assert updates["priority"]["priority_score"] is None
    assert updates["priority"]["valid_triage_available"] is False

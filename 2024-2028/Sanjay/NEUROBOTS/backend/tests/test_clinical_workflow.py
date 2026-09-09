from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.clinical_agents import SafetyAgent
from app.agents.contracts import ClinicalAgent
from app.agents.supervisor import (
    DeterministicSupervisorPolicy,
    SupervisorAction,
    SupervisorAgent,
    SupervisorDecision,
)
from app.db.models import AuditEvent
from app.services.clinical_workflow import run_clinical_assessment
from app.workflows.clinical_graph import build_clinical_graph
from app.workflows.clinical_state import create_initial_clinical_state
from tests.conftest import ApiClient


TRACE_FIELDS = {
    "agent",
    "status",
    "started_at",
    "completed_at",
    "duration_ms",
    "summary",
    "warnings",
    "errors",
}


def _create_encounter(client: ApiClient, patient_id: str, complaint: str) -> dict:
    response = client.post(
        f"/api/patients/{patient_id}/encounters",
        json={"encounter_type": "emergency", "chief_complaint": complaint},
    )
    assert response.status_code == 201
    return response.json()


def _add_demo_observations(client: ApiClient, encounter_id: str) -> tuple[dict, dict]:
    for symptom in (
        {"name": "  CHEST   Pain ", "severity": 8, "duration": "30 minutes"},
        {"name": "Shortness Of Breath", "severity": 7},
        {"name": "sweating", "severity": 6},
    ):
        response = client.post(
            f"/api/encounters/{encounter_id}/symptoms", json=symptom
        )
        assert response.status_code == 201

    manual = client.post(
        f"/api/encounters/{encounter_id}/vitals",
        json={
            "heart_rate": 112,
            "systolic_bp": 152,
            "diastolic_bp": 94,
            "spo2": 94,
            "respiratory_rate": 24,
            "temperature": 37,
            "measured_at": "2026-08-07T08:00:00Z",
            "source": "MANUAL",
        },
    ).json()
    simulated = client.post(
        f"/api/encounters/{encounter_id}/vitals",
        json={
            "heart_rate": 108,
            "systolic_bp": 148,
            "diastolic_bp": 90,
            "spo2": 95,
            "respiratory_rate": 22,
            "temperature": 37.1,
            "measured_at": "2026-08-07T08:05:00Z",
            "source": "SIMULATOR",
        },
    ).json()
    for lab in (
        {"test_name": "blood sugar", "value": 146, "unit": "mg/dL"},
        {"test_name": "CK-MB", "value": 8.4, "unit": "ng/mL"},
        {"test_name": "troponin", "value": 0.18, "unit": "ng/mL"},
    ):
        response = client.post(f"/api/encounters/{encounter_id}/labs", json=lab)
        assert response.status_code == 201
    return manual, simulated


def test_initial_state_is_complete_and_does_not_fabricate_assessments() -> None:
    state = create_initial_clinical_state("patient-1", "encounter-1")

    assert state["workflow_id"]
    assert state["workflow_status"] == "INITIALIZED"
    assert state["next_action"] is None
    assert state["completed_agents"] == []
    assert state["previous_vitals"] == []
    assert state["cardiac_risk"] is None
    assert state["triage"] is None
    assert state["priority"] is None


def test_graph_compiles_with_supervisor_return_edges(db_session: Session) -> None:
    graph = build_clinical_graph(db_session)
    drawable = graph.get_graph()
    edges = {(edge.source, edge.target) for edge in drawable.edges}

    assert ("__start__", "intake") in edges
    assert ("intake", "supervisor") in edges
    for specialist in (
        "patient_resolution",
        "multimodal",
        "clinical_nlp",
        "data_fusion",
        "triage_risk",
        "clinical_reasoning",
        "safety",
        "xai",
        "priority",
    ):
        assert (specialist, "supervisor") in edges
    assert ("patient_resolution", "multimodal") not in edges


def test_supervisor_routes_from_state_and_enforces_decision_limit() -> None:
    policy = DeterministicSupervisorPolicy()
    state = create_initial_clinical_state("patient-1", "encounter-1")

    assert policy.decide(state).action == SupervisorAction.PATIENT_RESOLUTION
    state["completed_agents"] = ["patient_resolution"]
    assert policy.decide(state).action == SupervisorAction.MULTIMODAL
    state["agent_trace"] = [
        {"agent": "supervisor", "status": "SUCCESS"}
        for _ in range(policy.max_decisions)
    ]
    limited = policy.decide(state)
    assert limited.action == SupervisorAction.FINISH
    assert limited.workflow_status == "FAILED"


class _LoopingSupervisorPolicy(DeterministicSupervisorPolicy):
    def decide(self, state):
        decision_count = sum(
            entry.get("agent") == "supervisor" for entry in state.get("agent_trace", [])
        )
        if decision_count >= self.max_decisions:
            return super().decide(state)
        return SupervisorDecision(
            SupervisorAction.PATIENT_RESOLUTION,
            "Adversarial test policy repeats one specialist",
        )


def test_compiled_graph_stops_an_adversarial_routing_loop(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"], "Loop protection test")
    graph = build_clinical_graph(
        db_session,
        supervisor=SupervisorAgent(_LoopingSupervisorPolicy()),
    )

    result = graph.invoke(
        create_initial_clinical_state(patient["id"], encounter["id"]),
        config={"recursion_limit": 32},
    )

    supervisor_entries = [
        entry for entry in result["agent_trace"] if entry["agent"] == "supervisor"
    ]
    assert len(supervisor_entries) == _LoopingSupervisorPolicy.max_decisions + 1
    assert result["workflow_status"] == "FAILED"
    assert result["next_action"] == "FINISH"


def test_workflow_api_runs_supervised_demo_and_preserves_clinical_data(
    client: ApiClient, patient: dict
) -> None:
    historical = _create_encounter(client, patient["id"], "Prior chest discomfort")
    client.post(
        f"/api/encounters/{historical['id']}/vitals",
        json={
            "heart_rate": 82,
            "measured_at": "2026-07-01T08:00:00Z",
            "source": "EHR",
        },
    )
    client.patch(f"/api/encounters/{historical['id']}", json={"status": "COMPLETED"})
    current = _create_encounter(client, patient["id"], "Suspected heart attack")
    manual, simulated = _add_demo_observations(client, current["id"])

    response = client.post(f"/api/encounters/{current['id']}/workflow")
    assert response.status_code == 200
    result = response.json()

    assert result["workflow_status"] == "COMPLETED"
    assert result["next_action"] == "FINISH"
    assert result["returning_patient"] is True
    assert [item["id"] for item in result["patient_history"]] == [historical["id"]]
    assert [item["name"] for item in result["normalized_symptoms"]] == [
        "chest pain",
        "shortness of breath",
        "sweating",
    ]
    assert all(item["source"] == "MANUAL" for item in result["normalized_symptoms"])
    assert result["current_vitals"]["id"] == simulated["id"]
    assert [item["id"] for item in result["previous_vitals"]] == [manual["id"]]
    assert result["fused_context"]["vitals"]["latest"]["source"] == "SIMULATOR"
    assert result["fused_context"]["vitals"]["previous"][0]["source"] == "MANUAL"
    assert result["fused_context"]["labs"]["latest_by_test"]["troponin"]["source"] == "MANUAL"
    assert set(result["current_labs"]) == {"bloodsugar", "ckmb", "troponin"}


def test_model_outputs_risk_triage_shap_and_independent_priority(
    client: ApiClient, patient: dict
) -> None:
    current = _create_encounter(client, patient["id"], "Chest pain")
    _add_demo_observations(client, current["id"])
    result = client.post(f"/api/encounters/{current['id']}/workflow").json()

    assert result["cardiac_risk"]["status"] == "SUCCESS"
    assert result["cardiac_risk"]["prediction"] in {0, 1}
    assert 0 <= result["cardiac_risk"]["probability"] <= 1
    assert result["cardiac_risk"]["model_version"] == "cardiac-risk-rf-1.0.0"
    assert result["triage"]["status"] == "SUCCESS"
    assert result["triage"]["severity_level"] == "PROTOTYPE_ESI_2"
    assert result["triage"]["prototype_esi_level"] == 2
    assert result["triage"]["provisional"] is True
    assert result["triage"]["esi"] is None
    assert result["triage"]["assigned_priority"] is None
    assert result["clinical_reasoning"]["status"] == "PENDING_CAPABILITY"
    assert result["clinical_reasoning"]["tool_boundary"]
    assert result["explanation"]["status"] == "PARTIAL"
    assert len(result["explanation"]["shap_values"]) == 8
    assert result["explanation"]["triage_rule_trace"]["policy_version"] == (
        "prototype-esi-subset-1.0.0"
    )
    assert result["explanation"]["decision_trace"]
    assert result["priority"]["status"] == "SUCCESS"
    assert result["priority"]["queue_entry_id"]
    assert result["priority"]["priority_band"] in {"CRITICAL", "VERY_HIGH"}
    assert result["priority"]["priority_score"] != result["cardiac_risk"]["probability"]
    assert result["priority"]["prototype_esi_level"] == 2
    assert result["explanation"]["priority_rule_trace"]["rules"]


def test_multimodal_capabilities_and_execution_trace_contract(
    client: ApiClient, patient: dict
) -> None:
    current = _create_encounter(client, patient["id"], "Chest pain")
    _add_demo_observations(client, current["id"])
    result = client.post(f"/api/encounters/{current['id']}/workflow").json()

    assert result["capability_status"]["ocr_extraction"]["status"] == "AVAILABLE"
    assert result["capability_status"]["speech_transcription"]["status"] == "PARTIAL"
    for capability_name in (
        "medical_image_interpretation",
        "wearable_telemetry",
    ):
        assert result["capability_status"][capability_name]["status"] == "PENDING_CAPABILITY"
    assert result["capability_status"]["structured_observation_ingestion"]["details"][
        "source_counts"
    ] == {"MANUAL": 7, "SIMULATOR": 1}

    trace = result["agent_trace"]
    assert all(TRACE_FIELDS <= entry.keys() for entry in trace)
    assert [entry["agent"] for entry in trace] == [
        "intake",
        "supervisor",
        "patient_resolution",
        "supervisor",
        "multimodal",
        "supervisor",
        "clinical_nlp",
        "supervisor",
        "data_fusion",
        "supervisor",
        "triage_risk",
        "supervisor",
        "clinical_reasoning",
        "supervisor",
        "priority",
        "supervisor",
        "safety",
        "supervisor",
        "xai",
        "supervisor",
    ]
    assert result["completed_agents"] == [
        "intake",
        "patient_resolution",
        "multimodal",
        "clinical_nlp",
        "data_fusion",
        "triage_risk",
        "clinical_reasoning",
        "priority",
        "safety",
        "xai",
    ]


def test_safety_clears_inconsistent_unavailable_outputs() -> None:
    state = create_initial_clinical_state("patient-1", "encounter-1")
    state["cardiac_risk"] = {
        "status": "PENDING_CAPABILITY",
        "prediction": 1,
        "probability": 0.99,
    }
    state["triage"] = {
        "status": "PENDING_CAPABILITY",
        "esi": 1,
        "assigned_priority": "critical",
    }

    updates = SafetyAgent()(state)
    assert updates["cardiac_risk"]["prediction"] is None
    assert updates["cardiac_risk"]["probability"] is None
    assert updates["triage"]["esi"] is None
    assert updates["triage"]["assigned_priority"] is None
    finding_types = {
        finding["type"] for finding in updates["safety_findings"]["findings"]
    }
    assert "INCONSISTENT_UNAVAILABLE_RISK_OUTPUT" in finding_types
    assert "INCONSISTENT_UNAVAILABLE_TRIAGE_OUTPUT" in finding_types


class _FailingNoncriticalAgent(ClinicalAgent):
    name = "multimodal"

    def run(self, state):
        raise RuntimeError("isolated test failure")


def test_noncritical_agent_failure_is_traceable_and_does_not_repeat() -> None:
    state = create_initial_clinical_state("patient-1", "encounter-1")
    state["completed_agents"] = ["patient_resolution"]
    updates = _FailingNoncriticalAgent()(state)
    state.update(updates)

    assert state["agent_trace"][-1]["status"] == "FAILED"
    assert state["workflow_halted"] is False
    assert "multimodal" in state["completed_agents"]
    assert DeterministicSupervisorPolicy().decide(state).action == SupervisorAction.CLINICAL_NLP


def test_nonexistent_encounter_fails_safely_and_emits_failed_audit(
    patient: dict, db_session: Session
) -> None:
    result = run_clinical_assessment(
        patient["id"], "missing-encounter", session=db_session
    )

    assert result["workflow_status"] == "FAILED"
    assert result["next_action"] == "FINISH"
    assert result["agent_trace"][0]["agent"] == "intake"
    assert result["agent_trace"][0]["status"] == "FAILED"
    assert result["agent_trace"][-1]["agent"] == "supervisor"
    assert result["errors"]
    events = list(
        db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.event_metadata["workflow_id"].as_string() == result["workflow_id"])
            .order_by(AuditEvent.timestamp)
        ).all()
    )
    assert [event.event_type for event in events] == [
        "CLINICAL_WORKFLOW_STARTED",
        "CLINICAL_WORKFLOW_FAILED",
    ]


def test_intake_rejects_encounter_owned_by_another_patient(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"], "Ownership check")
    other_response = client.post(
        "/api/patients",
        json={
            "external_patient_id": "HOSP-OTHER",
            "first_name": "Other",
            "last_name": "Patient",
            "date_of_birth": "1980-01-01",
            "gender": "unspecified",
        },
    )
    assert other_response.status_code == 201

    result = run_clinical_assessment(
        other_response.json()["id"], encounter["id"], session=db_session
    )

    assert result["workflow_status"] == "FAILED"
    assert "does not belong" in result["agent_trace"][0]["errors"][0]


def test_successful_workflow_emits_only_start_and_complete_audits(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    current = _create_encounter(client, patient["id"], "Chest pain")
    _add_demo_observations(client, current["id"])
    result = client.post(f"/api/encounters/{current['id']}/workflow").json()
    events = list(
        db_session.scalars(
            select(AuditEvent)
            .where(AuditEvent.event_metadata["workflow_id"].as_string() == result["workflow_id"])
            .order_by(AuditEvent.timestamp)
        ).all()
    )

    assert [event.event_type for event in events] == [
        "CLINICAL_WORKFLOW_STARTED",
        "CLINICAL_WORKFLOW_COMPLETED",
    ]
    assert events[-1].event_metadata["agent_count"] == len(result["agent_trace"])

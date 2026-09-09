from tests.conftest import ApiClient


def _complete_encounter(client: ApiClient, patient_id: str) -> str:
    encounter = client.post(
        f"/api/patients/{patient_id}/encounters",
        json={"encounter_type": "emergency", "chief_complaint": "Chest pain"},
    ).json()
    for name in ("chest pain", "sweating"):
        assert client.post(
            f"/api/encounters/{encounter['id']}/symptoms", json={"name": name}
        ).status_code == 201
    assert client.post(
        f"/api/encounters/{encounter['id']}/vitals",
        json={
            "heart_rate": 112,
            "systolic_bp": 152,
            "diastolic_bp": 94,
            "spo2": 94,
            "respiratory_rate": 24,
        },
    ).status_code == 201
    for lab in (
        {"test_name": "blood sugar", "value": 146},
        {"test_name": "CK-MB", "value": 8.4},
        {"test_name": "troponin", "value": 0.18},
    ):
        assert client.post(
            f"/api/encounters/{encounter['id']}/labs", json=lab
        ).status_code == 201
    return encounter["id"]


def test_error_envelopes_are_consistent(client: ApiClient, encounter: dict) -> None:
    missing = client.get("/api/patients/not-found")
    invalid = client.post(
        f"/api/encounters/{encounter['id']}/vitals", json={"spo2": 101}
    )

    assert missing.status_code == 404
    assert missing.json()["error"] == {
        "code": "ENTITY_NOT_FOUND",
        "detail": "patient 'not-found' was not found",
    }
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "INVALID_REQUEST"
    assert invalid.json()["error"]["issues"]


def test_cors_allows_only_configured_local_frontends(client: ApiClient) -> None:
    allowed = client.request(
        "OPTIONS",
        "/api/queue",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    disallowed = client.request(
        "OPTIONS",
        "/api/queue",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert disallowed.status_code == 400
    assert "access-control-allow-origin" not in disallowed.headers


def test_latest_assessment_and_history_are_clean_persisted_projections(
    client: ApiClient, patient: dict
) -> None:
    encounter_id = _complete_encounter(client, patient["id"])
    first = client.post(f"/api/encounters/{encounter_id}/workflow")
    second = client.post(f"/api/encounters/{encounter_id}/workflow")
    assert first.status_code == 200
    assert second.status_code == 200

    latest = client.get(f"/api/encounters/{encounter_id}/assessment")
    history = client.get(f"/api/encounters/{encounter_id}/assessment-history")

    assert latest.status_code == 200
    body = latest.json()
    assert body["patient"]["id"] == patient["id"]
    assert body["encounter"]["id"] == encounter_id
    assert body["cardiac_risk"]["status"] == "SUCCESS"
    assert body["triage"]["provisional"] is True
    assert body["priority"]["priority_band"] in {"CRITICAL", "VERY_HIGH"}
    assert body["explanation"]["feature_contributions"]
    assert body["clinical_reasoning"]["termination_reason"] == "PROVIDER_UNAVAILABLE"

    history_body = history.json()
    assert len(history_body["risk_predictions"]) == 2
    assert len(history_body["triage_assessments"]) == 2
    assert len(history_body["explanations"]) == 2
    assert len(history_body["clinical_reasoning_results"]) == 2
    assert len(history_body["priority_calculations"]) == 2

    queue = client.get("/api/queue").json()
    assert queue[0]["patient_display"] == {
        "display_name": "Mira Patel",
        "age_years": 48,
        "chief_complaint": "Chest pain",
    }


def test_legacy_groq_reasoning_records_are_rendered_provider_neutral(
    client: ApiClient, patient: dict, db_session
) -> None:
    from app.agents.clinical_reasoning_agent import AGENT_VERSION
    from app.db.models import ClinicalEncounter, ClinicalReasoningResult, Patient

    encounter = _complete_encounter(client, patient["id"])
    record = ClinicalReasoningResult(
        encounter_id=encounter,
        workflow_id="workflow-legacy-groq",
        agent_name="clinical_reasoning",
        agent_version=AGENT_VERSION,
        provider="groq",
        model="openai/gpt-oss-20b",
        schema_version="clinical-reasoning-output-1.0.0",
        summary="Groq request failed (ratelimit error)",
        structured_output={},
        retrieved_source_ids=[],
        knowledge_graph_evidence=[],
        tool_call_trace=[],
        termination_reason="PROVIDER_RATE_LIMITED",
        latency_ms=12.5,
    )
    db_session.add(record)
    db_session.commit()

    assessment = client.get(f"/api/encounters/{encounter}/assessment").json()
    reasoning = assessment["clinical_reasoning"]

    assert reasoning["provider"] == "gemini"
    assert reasoning["summary"] == "Clinical reasoning rate limit reached"
    assert reasoning["termination_reason"] == "PROVIDER_RATE_LIMITED"


def test_terminal_queue_status_cannot_be_reopened(client: ApiClient, patient: dict) -> None:
    encounter_id = _complete_encounter(client, patient["id"])
    workflow = client.post(f"/api/encounters/{encounter_id}/workflow").json()
    queue_id = workflow["priority"]["queue_entry_id"]
    assert client.patch(
        f"/api/queue/{queue_id}", json={"queue_status": "COMPLETED"}
    ).status_code == 200

    invalid = client.patch(
        f"/api/queue/{queue_id}", json={"queue_status": "WAITING"}
    )
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "INVALID_QUEUE_TRANSITION"


def test_openapi_hides_compatibility_and_simulator_routes(client: ApiClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/encounters/{encounter_id}/assessment" in schema["paths"]
    assert "/api/encounters/{encounter_id}/assessment-history" in schema["paths"]
    assert "/api/encounters/{encounter_id}/documents" in schema["paths"]
    assert "/api/encounters/{encounter_id}/speech" in schema["paths"]
    assert "/api/encounters/{encounter_id}/assessment-workflow" not in schema["paths"]
    assert "/api/encounters/{encounter_id}/simulate-vitals" not in schema["paths"]
    operation_ids = [
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))

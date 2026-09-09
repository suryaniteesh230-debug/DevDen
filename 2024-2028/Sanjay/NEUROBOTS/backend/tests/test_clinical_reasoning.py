from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.agents.clinical_agents import SafetyAgent
from app.agents.clinical_reasoning_agent import ClinicalReasoningAgent
from app.agents.reasoning_tools import (
    APPROVED_REASONING_TOOLS,
    ClinicalReasoningToolRegistry,
)
from app.clinical_reasoning.knowledge_graph import MedicalKnowledgeGraph
from app.clinical_reasoning.payloads import build_phi_minimized_reasoning_payload
from app.clinical_reasoning.retrieval import ClinicalKnowledgeRetriever
from app.clinical_reasoning.schemas import ClinicalReasoningOutput
from app.core.config import Settings, get_settings
from app.db.models import ClinicalReasoningResult
from app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMStructuredOutputError,
    LLMTimeoutError,
    ProviderTurn,
    ToolCallRequest,
)
from app.llm.gemini_provider import GeminiProvider
from app.workflows.clinical_graph import build_clinical_graph
from app.workflows.clinical_state import create_initial_clinical_state
from tests.conftest import ApiClient


def _valid_output(*evidence_refs: str) -> ClinicalReasoningOutput:
    refs = list(evidence_refs)
    return ClinicalReasoningOutput.model_validate(
        {
            "summary": "The available findings support urgent clinician assessment for a possible acute coronary syndrome while alternative causes remain possible.",
            "differential_considerations": [
                {
                    "condition": "Acute coronary syndrome",
                    "support_level": "HIGH",
                    "supporting_findings": ["Chest-pain symptom cluster"],
                    "contradicting_or_missing_findings": ["No ECG is available"],
                    "evidence_refs": refs,
                }
            ],
            "symptom_correlations": [
                {
                    "symptoms": ["chest pain", "shortness of breath"],
                    "associated_with": "Acute coronary syndrome",
                    "evidence_refs": refs,
                    "relationship_type": "ASSOCIATION",
                }
            ],
            "clinical_evidence": [],
            "knowledge_graph_evidence": [],
            "important_missing_information": ["12-lead ECG"],
            "clinical_considerations": [
                {
                    "consideration": "Prompt clinician-led emergency evaluation is warranted.",
                    "evidence_refs": refs or ["LOCAL-STATE"],
                }
            ],
            "uncertainty": "This is decision support from a small corpus and cannot confirm a diagnosis.",
            "tool_calls": [],
            "limitations": [
                "Not a diagnosis or treatment order",
                "The local corpus is intentionally narrow",
            ],
        }
    )


class ScriptedProvider(LLMProvider):
    provider_name = "gemini"
    model = "gemini-3.6-flash"

    def __init__(self, script: list[Any], *, available: bool = True) -> None:
        self.script = list(script)
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    def generate_with_tools(self, **_kwargs) -> ProviderTurn:
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, ToolCallRequest):
            return ProviderTurn(
                provider=self.provider_name,
                model=self.model,
                assistant_message={
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": item.id,
                            "type": "function",
                            "function": {
                                "name": item.name,
                                "arguments": json.dumps(item.arguments),
                            },
                        }
                    ],
                },
                tool_calls=[item],
                latency_ms=1.25,
            )
        return ProviderTurn(
            provider=self.provider_name,
            model=self.model,
            assistant_message={"role": "assistant", "content": item.model_dump_json()},
            structured_output=item,
            latency_ms=1.5,
        )

    def generate_structured(self, **kwargs) -> ProviderTurn:
        return self.generate_with_tools(**kwargs)


class FakeGeminiError(Exception):
    def __init__(self, status_code: int, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.response = SimpleNamespace(headers=headers or {}, status_code=status_code)


def _create_encounter(client: ApiClient, patient_id: str, complaint: str = "Chest pain") -> dict:
    response = client.post(
        f"/api/patients/{patient_id}/encounters",
        json={"encounter_type": "emergency", "chief_complaint": complaint},
    )
    assert response.status_code == 201
    return response.json()


def _add_complete_observations(client: ApiClient, encounter_id: str) -> None:
    for symptom in ("chest pain", "shortness of breath", "sweating"):
        assert client.post(
            f"/api/encounters/{encounter_id}/symptoms", json={"name": symptom}
        ).status_code == 201
    assert client.post(
        f"/api/encounters/{encounter_id}/vitals",
        json={
            "heart_rate": 112,
            "systolic_bp": 152,
            "diastolic_bp": 94,
            "spo2": 94,
            "respiratory_rate": 24,
            "temperature": 37,
        },
    ).status_code == 201
    for lab in (
        {"test_name": "blood sugar", "value": 146, "unit": "mg/dL"},
        {"test_name": "CK-MB", "value": 8.4, "unit": "ng/mL"},
        {"test_name": "troponin", "value": 0.18, "unit": "ng/mL"},
    ):
        assert client.post(
            f"/api/encounters/{encounter_id}/labs", json=lab
        ).status_code == 201


def test_gemini_provider_configuration_loads_exact_environment_names() -> None:
    settings = Settings(
        _env_file=None,
        GEMINI_API_KEY="test-only-key",
        GEMINI_MODEL="gemini-3.6-flash",
        GEMINI_MAX_RETRIES=2,
        GEMINI_MAX_OUTPUT_TOKENS=4096,
        GEMINI_THINKING_BUDGET=0,
    )
    assert settings.gemini_api_key.get_secret_value() == "test-only-key"
    assert "test-only-key" not in repr(settings)
    assert settings.gemini_model == "gemini-3.6-flash"
    assert settings.gemini_max_retries == 2
    assert settings.gemini_max_output_tokens == 4096
    assert settings.gemini_thinking_budget == 0


def test_missing_gemini_key_is_safe() -> None:
    provider = GeminiProvider(api_key="", model="gemini-3.6-flash")
    assert provider.available is False
    with pytest.raises(LLMProviderError, match="API key missing"):
        provider.generate_with_tools(
            messages=[], tools=[], output_schema=ClinicalReasoningOutput, timeout_seconds=1
        )


def test_gemini_provider_validates_structured_response_and_model() -> None:
    output = _valid_output()
    response = SimpleNamespace(model_version="gemini-3.6-flash", text=output.model_dump_json())
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **_kwargs: response))
    provider = GeminiProvider(
        api_key="test-only-key", model="gemini-3.6-flash", client=client
    )
    turn = provider.generate_structured(
        messages=[{"role": "user", "content": "test"}],
        output_schema=ClinicalReasoningOutput,
        timeout_seconds=1,
    )
    assert isinstance(turn.structured_output, ClinicalReasoningOutput)
    assert turn.model == "gemini-3.6-flash"


def test_gemini_provider_separates_tool_use_from_strict_structured_output() -> None:
    calls: list[dict[str, Any]] = []
    tool_call = SimpleNamespace(name="get_current_vitals", args={"purpose": "Check current physiology"})
    response = SimpleNamespace(
        model_version="gemini-3.6-flash",
        text="",
        function_calls=[tool_call],
    )

    def generate_content(**kwargs):
        calls.append(kwargs)
        return response

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    provider = GeminiProvider(
        api_key="test-only-key", model="gemini-3.6-flash", client=client
    )
    provider.generate_with_tools(
        messages=[{"role": "user", "content": "test"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_current_vitals",
                    "description": "Test tool",
                    "parameters": {"type": "object"},
                },
            }
        ],
        output_schema=ClinicalReasoningOutput,
        timeout_seconds=1,
    )
    assert "tools" in calls[0]["config"]
    assert "response_json_schema" not in calls[0]["config"]
    assert calls[0]["config"]["automatic_function_calling"]["disable"] is True
    assert calls[0]["config"]["max_output_tokens"] == 4096
    assert calls[0]["config"]["thinking_config"]["thinking_budget"] == 0


def test_gemini_provider_reports_exhausted_rate_limit_with_retry_after() -> None:
    exception = FakeGeminiError(429, headers={"retry-after": "2"})

    def generate_content(**_kwargs):
        raise exception

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    provider = GeminiProvider(
        api_key="test-only-key", model="gemini-3.6-flash", client=client
    )

    with pytest.raises(LLMRateLimitError, match="retry after 2 seconds"):
        provider.generate_structured(
            messages=[{"role": "user", "content": "test"}],
            output_schema=ClinicalReasoningOutput,
            timeout_seconds=1,
        )


def test_phi_minimized_payload_excludes_direct_identifiers() -> None:
    state = create_initial_clinical_state("database-patient-id", "database-encounter-id")
    state["patient"] = {
        "id": "database-patient-id",
        "external_patient_id": "HOSP-SECRET",
        "first_name": "Mira",
        "last_name": "Patel",
        "phone_number": "555-0142",
        "date_of_birth": "1978-04-18",
        "gender": "female",
    }
    state["encounter"] = {
        "id": "database-encounter-id",
        "patient_id": "database-patient-id",
        "started_at": "2026-08-08T00:00:00Z",
        "clinician_notes": "Contains direct identifiers",
    }
    state["normalized_symptoms"] = [{"id": "symptom-id", "name": "chest pain"}]
    state["current_vitals"] = {
        "id": "vitals-id",
        "encounter_id": "database-encounter-id",
        "heart_rate": 100,
        "source": "MANUAL",
    }
    serialized = json.dumps(build_phi_minimized_reasoning_payload(state))
    for forbidden in (
        "Mira",
        "Patel",
        "555-0142",
        "HOSP-SECRET",
        "database-patient-id",
        "database-encounter-id",
        "1978-04-18",
        "clinician_notes",
    ):
        assert forbidden not in serialized
    assert '"approximate_age_years": 48' in serialized


def test_local_corpus_and_persisted_vector_index_load() -> None:
    settings = get_settings()
    retriever = ClinicalKnowledgeRetriever(
        settings.clinical_corpus_path, settings.clinical_vector_index_path
    )
    assert len(retriever.chunks) == 12
    assert retriever.index_metadata["corpus_version"] == "acs-corpus-1.0.0"
    assert retriever.index_metadata["embedding_dimension"] == 4096
    assert Path(settings.clinical_vector_index_path).exists()


def test_retrieval_returns_provenance_and_rejects_unrelated_query() -> None:
    settings = get_settings()
    retriever = ClinicalKnowledgeRetriever(
        settings.clinical_corpus_path, settings.clinical_vector_index_path
    )
    relevant = retriever.retrieve("acute chest pain serial troponin ECG", top_k=3)
    assert relevant["status"] == "SUCCESS"
    assert relevant["results"]
    assert all(
        item["source_id"]
        and item["chunk_id"]
        and item["metadata"]["source_url"]
        for item in relevant["results"]
    )
    unrelated = retriever.retrieve(
        "quantum chromodynamics nebula telescope orchid", top_k=3
    )
    assert unrelated["status"] == "NO_RELEVANT_EVIDENCE"
    assert unrelated["results"] == []


def test_medical_knowledge_graph_loads_with_edge_provenance() -> None:
    graph = MedicalKnowledgeGraph(get_settings().medical_knowledge_graph_path)
    assert graph.metadata == {
        "graph_version": "acs-kg-1.0.0",
        "node_count": 17,
        "edge_count": 17,
    }
    for *_nodes, data in graph.graph.edges(data=True):
        assert data["source_id"]
        assert data["source_reference"]
        assert data["graph_version"] == "acs-kg-1.0.0"


def test_knowledge_graph_tool_returns_structured_evidence() -> None:
    graph = MedicalKnowledgeGraph(get_settings().medical_knowledge_graph_path)
    result = graph.query("chest pain acute coronary syndrome", max_results=3)
    assert result["status"] == "SUCCESS"
    assert result["results"][0].keys() >= {
        "edge_id",
        "source_concept",
        "relationship",
        "target_concept",
        "provenance",
        "relevance",
    }


def test_registry_exposes_only_five_approved_tools(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"])
    registry = ClinicalReasoningToolRegistry(
        db_session, patient_id=patient["id"], encounter_id=encounter["id"]
    )
    assert registry.names == APPROVED_REASONING_TOOLS
    assert tuple(item["function"]["name"] for item in registry.definitions()) == (
        APPROVED_REASONING_TOOLS
    )


def test_patient_context_tools_reuse_persisted_repositories(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    historical = _create_encounter(client, patient["id"], "Prior chest discomfort")
    client.post(
        f"/api/encounters/{historical['id']}/symptoms", json={"name": "chest pain"}
    )
    current = _create_encounter(client, patient["id"])
    _add_complete_observations(client, current["id"])
    registry = ClinicalReasoningToolRegistry(
        db_session, patient_id=patient["id"], encounter_id=current["id"]
    )
    history = registry.execute(
        "get_patient_history", {"purpose": "Check relevant history", "max_encounters": 3}
    )
    vitals = registry.execute(
        "get_current_vitals", {"purpose": "Review current physiology"}
    )
    labs = registry.execute(
        "get_current_labs", {"purpose": "Review current biomarkers"}
    )
    assert history["results"][0]["symptoms"][0]["name"] == "chest pain"
    assert "chief_complaint" not in history["results"][0]
    assert vitals["result"]["heart_rate"] == 112
    assert {item["test_name"] for item in labs["results"]} == {
        "blood sugar",
        "CK-MB",
        "troponin",
    }
    assert "id" not in json.dumps({"history": history, "vitals": vitals, "labs": labs})


def test_clinical_reasoning_agent_selects_tools_dynamically_and_persists_trace(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"])
    provider = ScriptedProvider(
        [
            ToolCallRequest(
                "call-1",
                "query_medical_knowledge_graph",
                {
                    "query": "chest pain acute coronary syndrome",
                    "max_results": 3,
                    "purpose": "Correlate the symptom with source-backed conditions",
                },
            ),
            ToolCallRequest(
                "call-2",
                "retrieve_clinical_guidelines",
                {
                    "query": "acute chest pain ECG serial troponin evaluation",
                    "top_k": 3,
                    "purpose": "Retrieve current evaluation evidence",
                },
            ),
            _valid_output("KG-ACS-001", "CHEST21-ECG-01"),
        ]
    )
    state = create_initial_clinical_state(patient["id"], encounter["id"])
    updates = ClinicalReasoningAgent(db_session, provider=provider)(state)
    reasoning = updates["clinical_reasoning"]
    assert reasoning["status"] == "SUCCESS"
    assert [item["tool"] for item in reasoning["tool_calls"]] == [
        "query_medical_knowledge_graph",
        "retrieve_clinical_guidelines",
    ]
    assert reasoning["clinical_evidence"]
    assert reasoning["knowledge_graph_evidence"]
    row = db_session.get(ClinicalReasoningResult, reasoning["result_id"])
    assert row is not None
    assert row.model == "gemini-3.6-flash"
    assert row.tool_call_trace == reasoning["tool_calls"]
    assert row.retrieved_source_ids


def test_different_encounters_can_take_different_mocked_tool_paths(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    first = _create_encounter(client, patient["id"], "First")
    second = _create_encounter(client, patient["id"], "Second")
    paths = []
    for encounter, tool_call in (
        (
            first,
            ToolCallRequest(
                "history",
                "get_patient_history",
                {"purpose": "Check prior relevant findings", "max_encounters": 2},
            ),
        ),
        (
            second,
            ToolCallRequest(
                "vitals",
                "get_current_vitals",
                {"purpose": "Check current physiology"},
            ),
        ),
    ):
        provider = ScriptedProvider([tool_call, _valid_output()])
        state = create_initial_clinical_state(patient["id"], encounter["id"])
        reasoning = ClinicalReasoningAgent(db_session, provider=provider)(state)[
            "clinical_reasoning"
        ]
        paths.append([item["tool"] for item in reasoning["tool_calls"]])
    assert paths == [["get_patient_history"], ["get_current_vitals"]]


def test_duplicate_tool_loop_is_blocked(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"])
    repeated = ToolCallRequest(
        "repeat-1",
        "get_current_labs",
        {"purpose": "Review biomarkers"},
    )
    provider = ScriptedProvider(
        [repeated, ToolCallRequest("repeat-2", repeated.name, repeated.arguments)]
    )
    state = create_initial_clinical_state(patient["id"], encounter["id"])
    reasoning = ClinicalReasoningAgent(db_session, provider=provider)(state)[
        "clinical_reasoning"
    ]
    assert reasoning["termination_reason"] == "DUPLICATE_TOOL_CALL"
    assert reasoning["tool_calls"][-1]["status"] == "DUPLICATE_BLOCKED"


def test_maximum_tool_call_protection_stops_loop(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"])
    provider = ScriptedProvider(
        [
            ToolCallRequest("one", "get_current_vitals", {"purpose": "Check vitals"}),
            ToolCallRequest("two", "get_current_labs", {"purpose": "Check labs"}),
        ]
    )
    state = create_initial_clinical_state(patient["id"], encounter["id"])
    reasoning = ClinicalReasoningAgent(
        db_session, provider=provider, max_tool_calls=1
    )(state)["clinical_reasoning"]
    assert reasoning["termination_reason"] == "MAX_TOOL_CALLS"
    assert len(reasoning["tool_calls"]) == 1


def test_structured_output_rejects_extra_probability_and_numeric_claim() -> None:
    payload = _valid_output().model_dump(mode="json")
    payload["differential_considerations"][0]["probability"] = 0.87
    with pytest.raises(ValidationError):
        ClinicalReasoningOutput.model_validate(payload)
    payload = _valid_output().model_dump(mode="json")
    payload["summary"] = "The probability of ACS is 87 percent."
    with pytest.raises(ValidationError, match="numeric disease probability"):
        ClinicalReasoningOutput.model_validate(payload)


def test_strict_reasoning_json_schema_marks_every_property_required() -> None:
    schema = ClinicalReasoningOutput.model_json_schema()

    def inspect_schema(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object" and "properties" in value:
                assert set(value["properties"]) == set(value.get("required", []))
                assert value.get("additionalProperties") is False
            for nested in value.values():
                inspect_schema(nested)
        elif isinstance(value, list):
            for nested in value:
                inspect_schema(nested)

    inspect_schema(schema)


def test_agent_uses_separate_strict_synthesis_after_tool_selection_finishes(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    class TwoPhaseProvider(ScriptedProvider):
        def __init__(self) -> None:
            super().__init__([])
            self.synthesis_called = False

        def generate_with_tools(self, **_kwargs) -> ProviderTurn:
            return ProviderTurn(
                provider=self.provider_name,
                model=self.model,
                assistant_message={"role": "assistant", "content": "Evidence is sufficient."},
                latency_ms=1,
            )

        def generate_structured(self, **_kwargs) -> ProviderTurn:
            self.synthesis_called = True
            output = _valid_output()
            return ProviderTurn(
                provider=self.provider_name,
                model=self.model,
                assistant_message={"role": "assistant", "content": output.model_dump_json()},
                structured_output=output,
                latency_ms=1,
            )

    encounter = _create_encounter(client, patient["id"])
    provider = TwoPhaseProvider()
    state = create_initial_clinical_state(patient["id"], encounter["id"])
    result = ClinicalReasoningAgent(db_session, provider=provider)(state)[
        "clinical_reasoning"
    ]
    assert provider.synthesis_called is True
    assert result["status"] == "SUCCESS"


@pytest.mark.parametrize(
    ("exception", "termination"),
    [
        (LLMStructuredOutputError("invalid"), "INVALID_OUTPUT"),
        (LLMTimeoutError("timeout"), "PROVIDER_TIMEOUT"),
        (LLMProviderError("provider failed"), "PROVIDER_FAILURE"),
    ],
)
def test_provider_failures_are_isolated_and_persisted(
    exception: Exception,
    termination: str,
    client: ApiClient,
    patient: dict,
    db_session: Session,
) -> None:
    encounter = _create_encounter(client, patient["id"])
    state = create_initial_clinical_state(patient["id"], encounter["id"])
    reasoning = ClinicalReasoningAgent(
        db_session, provider=ScriptedProvider([exception])
    )(state)["clinical_reasoning"]
    assert reasoning["status"] == "PARTIAL"
    assert reasoning["termination_reason"] == termination
    assert db_session.get(ClinicalReasoningResult, reasoning["result_id"]) is not None


def test_missing_key_result_persists_and_workflow_can_continue(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"])
    state = create_initial_clinical_state(patient["id"], encounter["id"])
    provider = ScriptedProvider([], available=False)
    updates = ClinicalReasoningAgent(db_session, provider=provider)(state)
    assert updates["clinical_reasoning"]["status"] == "PENDING_CAPABILITY"
    assert updates["clinical_reasoning"]["termination_reason"] == "PROVIDER_UNAVAILABLE"
    assert updates.get("workflow_halted", False) is False


def test_full_workflow_provider_failure_preserves_fast_path_and_xai(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"])
    _add_complete_observations(client, encounter["id"])
    reasoning_agent = ClinicalReasoningAgent(
        db_session, provider=ScriptedProvider([LLMTimeoutError("timeout")])
    )
    graph = build_clinical_graph(db_session, clinical_reasoning_agent=reasoning_agent)
    result = graph.invoke(
        create_initial_clinical_state(patient["id"], encounter["id"]),
        config={"recursion_limit": 32},
    )
    assert result["workflow_status"] == "COMPLETED"
    assert result["clinical_reasoning"]["termination_reason"] == "PROVIDER_TIMEOUT"
    assert result["cardiac_risk"]["status"] == "SUCCESS"
    assert result["triage"]["status"] == "SUCCESS"
    assert result["explanation"]["model_contributions"]
    assert result["explanation"]["triage_rule_trace"]
    assert result["explanation"]["clinical_reasoning_evidence"]["status"] == "PARTIAL"


def test_successful_workflow_updates_state_safety_and_three_xai_channels(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"])
    _add_complete_observations(client, encounter["id"])
    provider = ScriptedProvider(
        [
            ToolCallRequest(
                "rag",
                "retrieve_clinical_guidelines",
                {
                    "purpose": "Retrieve acute chest-pain evaluation evidence",
                    "query": "acute chest pain ECG serial troponin",
                    "top_k": 2,
                },
            ),
            _valid_output("CHEST21-ECG-01"),
        ]
    )
    graph = build_clinical_graph(
        db_session,
        clinical_reasoning_agent=ClinicalReasoningAgent(db_session, provider=provider),
    )
    result = graph.invoke(
        create_initial_clinical_state(patient["id"], encounter["id"]),
        config={"recursion_limit": 32},
    )
    assert result["clinical_reasoning"]["status"] == "SUCCESS"
    assert "clinical_reasoning:12-lead ECG" in result["missing_information"]
    safety_types = {
        item["type"] for item in result["safety_findings"]["findings"]
    }
    assert "INVALID_CLINICAL_REASONING_OUTPUT" not in safety_types
    explanation = result["explanation"]
    assert explanation["model_contributions"]
    assert explanation["triage_rule_trace"]
    assert explanation["clinical_reasoning_evidence"]["clinical_evidence"]


def test_safety_flags_reasoning_failure_and_excessive_certainty() -> None:
    state = create_initial_clinical_state("patient", "encounter")
    state["clinical_reasoning"] = {
        "status": "PARTIAL",
        "termination_reason": "PROVIDER_FAILURE",
    }
    findings = SafetyAgent()(state)["safety_findings"]["findings"]
    assert any(item["type"] == "CLINICAL_REASONING_UNAVAILABLE" for item in findings)

    output = _valid_output()
    state["clinical_reasoning"] = {
        "status": "SUCCESS",
        "result_id": "result",
        "provider": "gemini",
        "model": "openai/gpt-oss-20b",
        "agent_version": "v1",
        "schema_version": "v1",
        "termination_reason": "COMPLETE",
        "provider_latency_ms": 1,
        "latency_ms": 2,
        "retrieved_source_ids": [],
        "available_evidence_refs": [],
        "created_at": "2026-08-08T00:00:00Z",
        **output.model_dump(mode="json"),
        "summary": "This definitely proves acute coronary syndrome.",
    }
    findings = SafetyAgent()(state)["safety_findings"]["findings"]
    assert any(item["type"] == "EXCESSIVE_REASONING_CERTAINTY" for item in findings)

    state["clinical_reasoning"]["summary"] = "The probability of ACS is 87 percent."
    findings = SafetyAgent()(state)["safety_findings"]["findings"]
    assert any(
        item["type"] == "INVENTED_NUMERIC_DISEASE_PROBABILITY"
        for item in findings
    )


def test_reasoning_table_is_present_in_metadata(db_session: Session) -> None:
    assert "clinical_reasoning_results" in inspect(db_session.bind).get_table_names()


def test_reasoning_results_are_append_only(
    client: ApiClient, patient: dict, db_session: Session
) -> None:
    encounter = _create_encounter(client, patient["id"])
    state = create_initial_clinical_state(patient["id"], encounter["id"])
    for _ in range(2):
        provider = ScriptedProvider([_valid_output()])
        ClinicalReasoningAgent(db_session, provider=provider)(state)
    rows = list(
        db_session.scalars(
            select(ClinicalReasoningResult).where(
                ClinicalReasoningResult.encounter_id == encounter["id"]
            )
        ).all()
    )
    assert len(rows) == 2
    assert rows[0].id != rows[1].id

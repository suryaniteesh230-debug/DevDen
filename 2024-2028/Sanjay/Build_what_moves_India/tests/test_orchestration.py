from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from langgraph.errors import GraphRecursionError
from pydantic import ValidationError

from sahayi_api.agent import AgentRuntime
from sahayi_api.config import get_settings
from sahayi_api.main import app
from sahayi_api.orchestration import (
    ConversationTurnRequest,
    MAX_GRAPH_STEPS,
    build_conversation_graph,
    run_conversation_turn,
)
from sahayi_api.procedures import default_pack_root, load_procedure_registry


AADHAAR = "uidai-aadhaar-address-update"
PENSION = "kerala-ign-oap"


class FakeChatCompletions:
    def __init__(self, replies: list[object]) -> None:
        self.replies = replies
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def runtime_with_replies(replies: list[object]) -> tuple[AgentRuntime, FakeChatCompletions]:
    runtime = AgentRuntime(replace(get_settings(), agent_enabled=True, groq_api_key="test-key", agent_request_budget=10))
    responses = FakeChatCompletions(replies)
    runtime.client = SimpleNamespace(chat=SimpleNamespace(completions=responses))
    return runtime, responses


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def registry():
    return load_procedure_registry(default_pack_root())


@pytest.mark.anyio
async def test_local_intent_requires_confirmation_without_sending_message(registry) -> None:
    runtime = AgentRuntime(replace(get_settings(), agent_enabled=False))
    result = await run_conversation_turn(
        ConversationTurnRequest(
            locale="en",
            event_type="start",
            local_candidates=[{"service_id": AADHAAR, "confidence": 0.98}],
        ),
        registry,
        runtime,
        "test",
    )
    assert result.status == "ok"
    assert result.next_action == "confirm_service"
    assert result.state.confirmed is False
    assert result.state.candidate_service_ids == [AADHAAR]
    assert result.current_question is None


@pytest.mark.anyio
async def test_confirmation_starts_one_question_at_a_time_and_revalidates_state(registry) -> None:
    runtime = AgentRuntime(replace(get_settings(), agent_enabled=False))
    proposal = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="start", local_candidates=[{"service_id": AADHAAR, "confidence": 1.0}]),
        registry,
        runtime,
        "test",
    )
    question = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="confirm_service", confirmed_service_id=AADHAAR, state=proposal.state),
        registry,
        runtime,
        "test",
    )
    assert question.next_action == "ask_user"
    assert question.current_question.question_id == "mobile-auth-access"
    assert [action.value for action in question.actions if action.action_id == "answer"] == [True, False]

    invalid = await run_conversation_turn(
        ConversationTurnRequest(
            locale="en",
            event_type="answer",
            answer={"question_id": "accepted-poa-ready", "value": True},
            state=question.state,
        ),
        registry,
        runtime,
        "test",
    )
    assert invalid.status == "error"
    assert invalid.diagnostic_category == "invalid_state"


@pytest.mark.anyio
async def test_readiness_recomputes_and_preparation_fans_out_to_exact_pack_handoff(registry) -> None:
    runtime = AgentRuntime(replace(get_settings(), agent_enabled=False))
    result = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="start", local_candidates=[{"service_id": AADHAAR, "confidence": 1.0}]),
        registry,
        runtime,
        "test",
    )
    result = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="confirm_service", confirmed_service_id=AADHAAR, state=result.state),
        registry,
        runtime,
        "test",
    )
    for value in (True, "own-document", True):
        result = await run_conversation_turn(
            ConversationTurnRequest(
                locale="en",
                event_type="answer",
                answer={"question_id": result.current_question.question_id, "value": value},
                state=result.state,
            ),
            registry,
            runtime,
            "test",
        )
    assert result.readiness.complete is True
    assert result.checklist is not None
    assert result.preparation is not None
    assert result.preparation.watermark == "DEMO — NOT FOR SUBMISSION"
    assert result.current_preparation_question is not None
    assert result.current_preparation_question.field_id == "new-address"
    result.state.completed_field_ids = ["new-address"]
    result = await run_conversation_turn(
        ConversationTurnRequest(
            locale="en",
            event_type="field_completed",
            completed_field_id="new-address",
            state=result.state,
        ),
        registry,
        runtime,
        "test",
    )
    assert result.current_preparation_question is None
    assert str(result.official_handoff_url) == str(registry[AADHAAR].pack.official_handoff_url)
    assert result.next_action == "official_handoff"


@pytest.mark.anyio
async def test_document_worker_accepts_only_confirmed_pack_allowlisted_evidence(registry) -> None:
    runtime = AgentRuntime(replace(get_settings(), agent_enabled=False))
    result = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="start", local_candidates=[{"service_id": AADHAAR, "confidence": 1.0}]),
        registry,
        runtime,
        "test",
    )
    result = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="confirm_service", confirmed_service_id=AADHAAR, state=result.state),
        registry,
        runtime,
        "test",
    )
    accepted = await run_conversation_turn(
        ConversationTurnRequest(
            locale="en",
            event_type="document_evidence",
            document_evidence={"document_id": "valid-proof-of-address", "appears_relevant": True, "citizen_confirmed": True},
            state=result.state,
        ),
        registry,
        runtime,
        "test",
    )
    assert accepted.accepted_document_evidence[0].document_id == "valid-proof-of-address"

    rejected = await run_conversation_turn(
        ConversationTurnRequest(
            locale="en",
            event_type="document_evidence",
            document_evidence={"document_id": "invented-document", "appears_relevant": True, "citizen_confirmed": True},
            state=result.state,
        ),
        registry,
        runtime,
        "test",
    )
    assert rejected.status == "error"

    with pytest.raises(ValidationError):
        ConversationTurnRequest.model_validate({
            "locale": "en",
            "event_type": "document_evidence",
            "document_evidence": {
                "document_id": "valid-proof-of-address",
                "appears_relevant": True,
                "citizen_confirmed": True,
                "raw_ocr_text": "forbidden",
            },
        })


@pytest.mark.anyio
async def test_confirmed_ocr_maps_only_structural_field_completion_and_never_a_value(registry) -> None:
    runtime = AgentRuntime(replace(get_settings(), agent_enabled=False))
    proposal = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="start", local_candidates=[{"service_id": AADHAAR, "confidence": 1.0}]),
        registry,
        runtime,
        "test",
    )
    result = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="confirm_service", confirmed_service_id=AADHAAR, state=proposal.state),
        registry,
        runtime,
        "test",
    )
    result.state.completed_field_ids = ["proof-of-address-document"]
    result = await run_conversation_turn(
        ConversationTurnRequest(
            locale="en",
            event_type="document_evidence",
            document_evidence={"document_id": "valid-proof-of-address", "appears_relevant": True, "citizen_confirmed": True},
            state=result.state,
        ),
        registry,
        runtime,
        "test",
    )
    assert result.state.completed_field_ids == ["proof-of-address-document"]
    assert next(field for field in result.preparation.fields if field.field_id == "proof-of-address-document").value is None


@pytest.mark.anyio
async def test_complete_kerala_preparation_asks_each_local_required_field_once(registry) -> None:
    runtime = AgentRuntime(replace(get_settings(), agent_enabled=False))
    result = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="start", local_candidates=[{"service_id": PENSION, "confidence": 1.0}]),
        registry,
        runtime,
        "test",
    )
    result = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="confirm_service", confirmed_service_id=PENSION, state=result.state),
        registry,
        runtime,
        "test",
    )
    for value in ("yes", "yes", "within", "no", "no", "no"):
        result = await run_conversation_turn(
            ConversationTurnRequest(
                locale="en",
                event_type="answer",
                answer={"question_id": result.current_question.question_id, "value": value},
                state=result.state,
            ),
            registry,
            runtime,
            "test",
        )
    asked = []
    while result.current_preparation_question is not None:
        field_id = result.current_preparation_question.field_id
        asked.append(field_id)
        result.state.completed_field_ids = sorted({*result.state.completed_field_ids, field_id})
        result = await run_conversation_turn(
            ConversationTurnRequest(locale="en", event_type="field_completed", completed_field_id=field_id, state=result.state),
            registry,
            runtime,
            "test",
        )
    assert asked == ["applicant-name", "gender-category", "contact-and-address"]
    assert result.next_action == "official_handoff"
    assert result.missing_required_field_ids == []


@pytest.mark.anyio
async def test_hidden_readiness_derived_fields_do_not_count_on_another_route(registry) -> None:
    runtime = AgentRuntime(replace(get_settings(), agent_enabled=False))
    result = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="start", local_candidates=[{"service_id": AADHAAR, "confidence": 1.0}]),
        registry,
        runtime,
        "test",
    )
    result = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="confirm_service", confirmed_service_id=AADHAAR, state=result.state),
        registry,
        runtime,
        "test",
    )
    result = await run_conversation_turn(
        ConversationTurnRequest(
            locale="en",
            event_type="answer",
            answer={"question_id": result.current_question.question_id, "value": True},
            state=result.state,
        ),
        registry,
        runtime,
        "test",
    )
    result = await run_conversation_turn(
        ConversationTurnRequest(
            locale="en",
            event_type="answer",
            answer={"question_id": result.current_question.question_id, "value": "head-of-family"},
            state=result.state,
        ),
        registry,
        runtime,
        "test",
    )
    result = await run_conversation_turn(
        ConversationTurnRequest(
            locale="en",
            event_type="answer",
            answer={"question_id": result.current_question.question_id, "value": True},
            state=result.state,
        ),
        registry,
        runtime,
        "test",
    )
    assert result.current_preparation_question.field_id == "new-address"
    assert "poa-ready" not in result.missing_required_field_ids
    assert result.preparation_field_count == 4


@pytest.mark.anyio
async def test_mocked_cloud_clarification_is_one_call_and_still_requires_confirmation(registry) -> None:
    output = {
        "guidance_message": "I found the verified Kerala pension procedure.",
        "selection_state": "selected",
        "service_id": PENSION,
        "action_ids": ["view-procedure"],
    }
    message = SimpleNamespace(content=json.dumps(output), tool_calls=None)
    runtime, responses = runtime_with_replies([SimpleNamespace(choices=[SimpleNamespace(message=message)])])
    result = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="cloud_clarification", message="Help with an old age pension", consent=True),
        registry,
        runtime,
        "test",
    )
    assert len(responses.calls) == 1
    assert result.next_action == "confirm_service"
    assert result.state.candidate_service_ids == [PENSION]
    assert result.state.confirmed is False


@pytest.mark.anyio
async def test_ai_disabled_and_provider_failure_return_deterministic_safe_fallback(registry) -> None:
    disabled = AgentRuntime(replace(get_settings(), agent_enabled=False, groq_api_key=None))
    unavailable = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="cloud_clarification", message="Please clarify this service", consent=True),
        registry,
        disabled,
        "test",
    )
    assert unavailable.status == "unavailable"
    assert unavailable.diagnostic_category == "provider_unavailable"

    failing, responses = runtime_with_replies([RuntimeError("private provider detail")])
    fallback = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="cloud_clarification", message="Please clarify this service", consent=True),
        registry,
        failing,
        "test",
    )
    assert len(responses.calls) == 1
    assert fallback.status == "unavailable"
    assert "private provider detail" not in fallback.assistant_message


def test_graph_has_no_checkpointer_store_or_persistent_thread(registry) -> None:
    graph = build_conversation_graph(registry, AgentRuntime(replace(get_settings(), agent_enabled=False)), "test")
    graph_nodes = set(graph.get_graph().nodes)
    assert graph.checkpointer is None
    assert graph.store is None
    assert MAX_GRAPH_STEPS == 12
    assert len(graph_nodes - {"__start__", "__end__"}) <= MAX_GRAPH_STEPS
    assert {"safety_consent", "intent_clarification", "procedure_router", "document_evidence", "interview_readiness", "checklist", "preparation", "explanation", "official_handoff"} <= graph_nodes


@pytest.mark.anyio
async def test_unknown_service_is_rejected_without_provider_or_procedure_facts(registry) -> None:
    runtime = AgentRuntime(replace(get_settings(), agent_enabled=False))
    result = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="start", local_candidates=[{"service_id": "invented-service", "confidence": 1.0}]),
        registry,
        runtime,
        "test",
    )
    assert result.status == "error"
    assert result.diagnostic_category == "invalid_state"
    assert result.active_procedure is None
    assert result.official_handoff_url is None


@pytest.mark.anyio
async def test_graph_recursion_limit_fails_closed_with_bounded_diagnostic(registry, monkeypatch) -> None:
    class ExhaustedGraph:
        def invoke(self, *_args, **_kwargs):
            raise GraphRecursionError("synthetic bounded test")

    monkeypatch.setattr("sahayi_api.orchestration.build_conversation_graph", lambda *_args: ExhaustedGraph())
    result = await run_conversation_turn(
        ConversationTurnRequest(locale="en", event_type="start", local_candidates=[{"service_id": AADHAAR, "confidence": 1.0}]),
        registry,
        AgentRuntime(replace(get_settings(), agent_enabled=False)),
        "test",
    )
    assert result.status == "error"
    assert result.diagnostic_category == "budget_exhausted"
    assert result.next_action == "error"


def test_turn_schema_forbids_unknown_fields_and_raw_message_without_consent() -> None:
    with pytest.raises(ValidationError):
        ConversationTurnRequest.model_validate({"locale": "en", "event_type": "start", "message": "local words"})
    with pytest.raises(ValidationError):
        ConversationTurnRequest.model_validate({"locale": "en", "event_type": "start", "metadata": {"x": 1}})
    with pytest.raises(ValidationError):
        ConversationTurnRequest.model_validate({"locale": "en", "event_type": "cloud_clarification", "message": "help", "consent": False})
    with pytest.raises(ValidationError):
        ConversationTurnRequest.model_validate({
            "locale": "en",
            "event_type": "field_completed",
            "completed_field_id": "new-address",
            "field_value": "must remain in browser memory",
        })


@pytest.mark.anyio
async def test_conversation_endpoint_is_strict_and_no_store() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/conversation/turn",
            json={"locale": "en", "event_type": "start", "local_candidates": [{"service_id": AADHAAR, "confidence": 0.9}]},
        )
        extra = await client.post("/api/v1/conversation/turn", json={"locale": "en", "event_type": "start", "file": "forbidden"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["next_action"] == "confirm_service"
    assert extra.status_code == 422
    assert extra.json() == {"error": "Invalid request"}

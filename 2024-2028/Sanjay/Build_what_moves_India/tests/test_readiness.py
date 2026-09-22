from __future__ import annotations

import copy
import json
import logging

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from sahayi_api.main import app
from sahayi_api.procedures import (
    MAX_RULE_DEPTH,
    MAX_RULE_LIST_SIZE,
    ProcedurePack,
    RuleExpression,
    default_pack_root,
    load_procedure_registry,
)
from sahayi_api.readiness import (
    OperationBudget,
    ReadinessInputError,
    evaluate_expression,
    evaluate_readiness,
)

PACK_PATH = default_pack_root() / "uidai-aadhaar-address-update" / "1.5.0" / "pack.json"
KERALA_PACK_PATH = default_pack_root() / "kerala-ign-oap" / "1.3.0" / "pack.json"


def pack_data() -> dict:
    return json.loads(PACK_PATH.read_text(encoding="utf-8"))


def loaded_procedure():
    return load_procedure_registry(default_pack_root())["uidai-aadhaar-address-update"]


def loaded_kerala_procedure():
    return load_procedure_registry(default_pack_root())["kerala-ign-oap"]


@pytest.mark.parametrize(
    ("answers", "outcome_id", "status"),
    [
        ({"age-60-or-higher": "no"}, "age-preliminary-mismatch", "alternative_path"),
        ({"age-60-or-higher": "yes", "kerala-residence-three-years": "no"}, "residence-preliminary-mismatch", "alternative_path"),
        ({"age-60-or-higher": "yes", "kerala-residence-three-years": "yes", "family-income-category": "above"}, "income-preliminary-mismatch", "alternative_path"),
        ({"age-60-or-higher": "yes", "kerala-residence-three-years": "yes", "family-income-category": "within", "service-or-family-pension": "no", "income-tax-payer": "yes"}, "tax-preliminary-mismatch", "alternative_path"),
        ({"age-60-or-higher": "yes", "kerala-residence-three-years": "yes", "family-income-category": "within", "service-or-family-pension": "yes"}, "pension-local-body-review", "cannot_confirm"),
        ({"age-60-or-higher": "yes", "kerala-residence-three-years": "yes", "family-income-category": "prefer-not-to-answer"}, "more-information-needed", "needs_information"),
        ({"age-60-or-higher": "yes", "kerala-residence-three-years": "yes", "family-income-category": "within", "service-or-family-pension": "no", "income-tax-payer": "no", "other-social-welfare-pension": "no"}, "preliminary-conditions-aligned", "ready"),
    ],
)
def test_kerala_readiness_golden_outcomes(answers: dict, outcome_id: str, status: str) -> None:
    result = evaluate_readiness(loaded_kerala_procedure(), answers)
    payload = result.model_dump(mode="json")
    assert result.complete is True
    assert result.outcome and result.outcome.outcome_id == outcome_id
    assert result.evaluation_status == status
    assert "answers" not in payload
    assert "2000" not in json.dumps(payload)


def test_kerala_sensitive_question_metadata_and_withheld_answer_are_safe() -> None:
    initial = evaluate_readiness(loaded_kerala_procedure(), {})
    assert initial.next_question and initial.next_question.sensitivity.value == "non_sensitive"
    income = evaluate_readiness(loaded_kerala_procedure(), {"age-60-or-higher": "yes", "kerala-residence-three-years": "yes"})
    assert income.next_question and income.next_question.sensitivity.value == "sensitive"
    assert "Prefer not to answer" in [option.label for option in income.next_question.options or []]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as api_client:
        yield api_client


@pytest.mark.parametrize(
    ("expression", "answers", "expected"),
    [
        ({"op": "all", "expressions": [{"op": "known", "question_id": "a"}, {"op": "equals", "question_id": "a", "value": True}]}, {"a": True}, True),
        ({"op": "any", "expressions": [{"op": "known", "question_id": "missing"}, {"op": "equals", "question_id": "a", "value": True}]}, {"a": True}, True),
        ({"op": "not", "expression": {"op": "known", "question_id": "missing"}}, {}, True),
        ({"op": "known", "question_id": "a"}, {"a": 3}, True),
        ({"op": "equals", "question_id": "a", "value": 3}, {"a": 3}, True),
        ({"op": "in", "question_id": "a", "values": ["one", "two"]}, {"a": "two"}, True),
        ({"op": "lt", "question_id": "a", "value": 4}, {"a": 3}, True),
        ({"op": "lte", "question_id": "a", "value": 3}, {"a": 3}, True),
        ({"op": "gt", "question_id": "a", "value": 2}, {"a": 3}, True),
        ({"op": "gte", "question_id": "a", "value": 3}, {"a": 3}, True),
    ],
)
def test_each_ast_operator(expression: dict, answers: dict, expected: bool) -> None:
    parsed = RuleExpression.model_validate(expression)
    assert evaluate_expression(parsed, answers, OperationBudget()) is expected


def test_expression_shapes_operators_and_list_sizes_are_strict() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        RuleExpression.model_validate({"op": "execute", "question_id": "a"})
    with pytest.raises(ValidationError, match="requires exactly"):
        RuleExpression.model_validate({"op": "known", "question_id": "a", "value": True})
    with pytest.raises(ValidationError, match="too_long"):
        RuleExpression.model_validate(
            {"op": "all", "expressions": [{"op": "known", "question_id": f"q-{index}"} for index in range(MAX_RULE_LIST_SIZE + 1)]}
        )


def test_unknown_references_operator_combinations_and_priorities_are_rejected() -> None:
    unknown = pack_data()
    unknown["readiness"]["rules"][0]["expression"]["question_id"] = "not-defined"
    with pytest.raises(ValidationError, match="unknown question reference"):
        ProcedurePack.model_validate(unknown)

    invalid_operator = pack_data()
    invalid_operator["readiness"]["rules"][0]["expression"] = {
        "op": "gt", "question_id": "mobile-auth-access", "value": 1
    }
    with pytest.raises(ValidationError, match="comparison operators require an integer"):
        ProcedurePack.model_validate(invalid_operator)

    duplicate = pack_data()
    duplicate["readiness"]["rules"][1]["priority"] = duplicate["readiness"]["rules"][0]["priority"]
    with pytest.raises(ValidationError, match="rule priorities must be unique"):
        ProcedurePack.model_validate(duplicate)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data["readiness"]["questions"][1].update(question_id="mobile-auth-access"), "question IDs must be unique"),
        (lambda data: data["readiness"]["questions"][1]["options"][1].update(option_id="own-document"), "question option IDs must be unique"),
        (lambda data: data["readiness"]["outcomes"][1].update(outcome_id="own-document-ready"), "outcome IDs must be unique"),
        (lambda data: data["readiness"]["rules"][1].update(rule_id="no-mobile-auth"), "rule IDs must be unique"),
        (lambda data: data["readiness"]["rules"][0].update(outcome_id="not-defined"), "unknown outcome reference"),
        (lambda data: data["readiness"]["questions"][0].update(source_ids=["not-a-source"]), "unknown source references"),
    ],
)
def test_duplicate_ids_and_readiness_references_are_rejected(mutation, message: str) -> None:
    data = pack_data()
    mutation(data)
    with pytest.raises(ValidationError, match=message):
        ProcedurePack.model_validate(data)


def test_safe_default_and_visibility_order_are_enforced() -> None:
    multiple_defaults = pack_data()
    multiple_defaults["readiness"]["outcomes"][0]["is_default"] = True
    with pytest.raises(ValidationError, match="exactly one needs_information default"):
        ProcedurePack.model_validate(multiple_defaults)

    unsafe_default = pack_data()
    unsafe_default["readiness"]["outcomes"][-1]["status"] = "ready"
    with pytest.raises(ValidationError, match="exactly one needs_information default"):
        ProcedurePack.model_validate(unsafe_default)

    forward_reference = pack_data()
    forward_reference["readiness"]["questions"][0]["visible_when"] = {
        "op": "known", "question_id": "address-update-route"
    }
    with pytest.raises(ValidationError, match="visibility may reference only earlier"):
        ProcedurePack.model_validate(forward_reference)


def test_depth_node_and_evaluation_operation_limits() -> None:
    expression: dict = {"op": "known", "question_id": "mobile-auth-access"}
    for _ in range(MAX_RULE_DEPTH):
        expression = {"op": "not", "expression": expression}
    too_deep = pack_data()
    too_deep["readiness"]["rules"][0]["expression"] = expression
    with pytest.raises(ValidationError, match="maximum depth"):
        ProcedurePack.model_validate(too_deep)

    too_many_nodes = pack_data()
    base_rule = too_many_nodes["readiness"]["rules"][0]
    too_many_nodes["readiness"]["rules"] = []
    for index in range(8):
        rule = copy.deepcopy(base_rule)
        rule["rule_id"] = f"large-rule-{index}"
        rule["priority"] = index + 1
        rule["expression"] = {
            "op": "all",
            "expressions": [{"op": "known", "question_id": "mobile-auth-access"} for _ in range(MAX_RULE_LIST_SIZE)],
        }
        too_many_nodes["readiness"]["rules"].append(rule)
    with pytest.raises(ValidationError, match="total nodes"):
        ProcedurePack.model_validate(too_many_nodes)

    parsed = RuleExpression.model_validate(
        {"op": "all", "expressions": [{"op": "known", "question_id": "a"}, {"op": "known", "question_id": "b"}]}
    )
    with pytest.raises(ReadinessInputError, match="budget"):
        evaluate_expression(parsed, {"a": True, "b": True}, OperationBudget(limit=2))


def test_answers_are_strict_and_revalidated() -> None:
    loaded = loaded_procedure()
    for invalid in ("true", 1):
        with pytest.raises(ReadinessInputError, match="Invalid readiness answer"):
            evaluate_readiness(loaded, {"mobile-auth-access": invalid})
    with pytest.raises(ReadinessInputError, match="Unknown readiness question"):
        evaluate_readiness(loaded, {"canary-unknown": True})
    with pytest.raises(ReadinessInputError, match="Invalid readiness answer"):
        evaluate_readiness(loaded, {"mobile-auth-access": True, "address-update-route": "not-an-option"})
    with pytest.raises(ReadinessInputError, match="inapplicable question"):
        evaluate_readiness(loaded, {"mobile-auth-access": False, "address-update-route": "own-document"})


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data["readiness"]["questions"][0].update(required="true"),
        lambda data: data["readiness"]["rules"][0].update(priority="10"),
        lambda data: data["readiness"]["outcomes"][0].update(is_default="false"),
    ],
)
def test_pack_readiness_booleans_and_numbers_are_strict(mutation) -> None:
    data = pack_data()
    mutation(data)
    with pytest.raises(ValidationError):
        ProcedurePack.model_validate(data)


def test_integer_bounds_are_enforced_by_generic_evaluator() -> None:
    data = pack_data()
    data["readiness"]["questions"][0].update(answer_type="integer", minimum=1, maximum=3)
    data["assistance"]["personas"][0]["readiness_answers"]["mobile-auth-access"] = 1

    def replace_boolean_constants(expression: dict) -> None:
        if expression.get("question_id") == "mobile-auth-access" and expression.get("op") == "equals":
            expression["value"] = 1 if expression["value"] is True else 2
        for child in expression.get("expressions", []):
            replace_boolean_constants(child)
        if "expression" in expression:
            replace_boolean_constants(expression["expression"])

    for question in data["readiness"]["questions"]:
        if question["visible_when"]:
            replace_boolean_constants(question["visible_when"])
    for rule in data["readiness"]["rules"]:
        replace_boolean_constants(rule["expression"])
    data["readiness"]["rules"][0]["expression"] = {
        "op": "gte", "question_id": "mobile-auth-access", "value": 1
    }
    validated = ProcedurePack.model_validate(data)
    loaded = loaded_procedure().model_copy(update={"pack": validated})
    with pytest.raises(ReadinessInputError, match="Invalid readiness answer"):
        evaluate_readiness(loaded, {"mobile-auth-access": 4})


def test_missing_answer_returns_next_question_without_echoing_answers() -> None:
    result = evaluate_readiness(loaded_procedure(), {"mobile-auth-access": True})
    payload = result.model_dump(mode="json")
    assert result.complete is False
    assert result.evaluation_status == "incomplete"
    assert result.next_question.question_id == "address-update-route"
    assert result.progress.answered == 1
    assert "answers" not in payload
    assert True not in payload.values()


@pytest.mark.parametrize(
    ("answers", "status", "outcome_id"),
    [
        ({"mobile-auth-access": False}, "alternative_path", "use-alternative-channel"),
        ({"mobile-auth-access": True, "address-update-route": "own-document", "accepted-poa-ready": True}, "ready", "own-document-ready"),
        ({"mobile-auth-access": True, "address-update-route": "own-document", "accepted-poa-ready": False}, "needs_information", "review-document-guidance"),
        ({"mobile-auth-access": True, "address-update-route": "head-of-family", "hof-participation-ready": True}, "ready", "hof-ready"),
        ({"mobile-auth-access": True, "address-update-route": "head-of-family", "hof-participation-ready": False}, "needs_information", "confirm-hof-participation"),
        ({"mobile-auth-access": True, "address-update-route": "unsure"}, "cannot_confirm", "route-cannot-confirm"),
    ],
)
def test_golden_aadhaar_paths(answers: dict, status: str, outcome_id: str) -> None:
    first = evaluate_readiness(loaded_procedure(), answers)
    second = evaluate_readiness(loaded_procedure(), dict(reversed(list(answers.items()))))
    assert first.complete is True
    assert first.evaluation_status == status
    assert first.outcome.outcome_id == outcome_id
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.sources
    assert any(entry.trace_type == "rule" for entry in first.reason_trace)
    assert first.disclaimer.endswith("not an eligibility decision or official approval.")


@pytest.mark.parametrize(
    ("loaded", "answers", "outcome_id", "handoff"),
    [
        (loaded_procedure, {"mobile-auth-access": True, "address-update-route": "own-document", "accepted-poa-ready": True}, "own-document-ready", "https://myaadhaar.uidai.gov.in/"),
        (loaded_kerala_procedure, {"age-60-or-higher": "yes", "kerala-residence-three-years": "yes", "family-income-category": "within", "service-or-family-pension": "no", "income-tax-payer": "no", "other-social-welfare-pension": "no"}, "preliminary-conditions-aligned", "https://welfarepension.lsgkerala.gov.in/ApplicationFormsEng.aspx"),
    ],
)
def test_localized_readiness_preserves_rule_outcomes_and_sources(loaded, answers: dict, outcome_id: str, handoff: str) -> None:
    results = {locale: evaluate_readiness(loaded(), answers, locale=locale) for locale in ("en", "hi", "ml")}
    assert len({result.outcome.title for result in results.values() if result.outcome}) == 3
    for locale, result in results.items():
        assert result.locale == locale
        assert result.outcome and result.outcome.outcome_id == outcome_id
        assert result.evaluation_status == "ready"
        assert str(result.official_handoff_url) == handoff
        assert [(source.source_id, str(source.url)) for source in result.sources] == [
            (source.source_id, str(source.url)) for source in results["en"].sources
        ]
        assert [(trace.trace_type, trace.trace_id, trace.source_ids) for trace in result.reason_trace] == [
            (trace.trace_type, trace.trace_id, trace.source_ids) for trace in results["en"].reason_trace
        ]


def test_safe_default_outcome_is_used() -> None:
    data = pack_data()
    data["readiness"]["rules"] = [rule for rule in data["readiness"]["rules"] if rule["rule_id"] != "own-document-not-ready"]
    validated = ProcedurePack.model_validate(data)
    loaded = loaded_procedure().model_copy(update={"pack": validated})
    result = evaluate_readiness(
        loaded,
        {"mobile-auth-access": True, "address-update-route": "own-document", "accepted-poa-ready": False},
    )
    assert result.outcome.outcome_id == "safe-default"
    assert result.evaluation_status == "needs_information"
    assert result.reason_trace[0].trace_type == "default"


@pytest.mark.anyio
async def test_stateless_api_progress_outcome_and_no_store(client: AsyncClient) -> None:
    endpoint = "/api/v1/procedures/uidai-aadhaar-address-update/readiness/evaluate"
    incomplete = await client.post(endpoint, json={"answers": {}})
    complete = await client.post(endpoint, json={"answers": {"mobile-auth-access": False}})
    repeated = await client.post(endpoint, json={"answers": {}})
    assert incomplete.status_code == complete.status_code == repeated.status_code == 200
    assert incomplete.json() == repeated.json()
    assert incomplete.json()["next_question"]["question_id"] == "mobile-auth-access"
    assert complete.json()["outcome"]["outcome_id"] == "use-alternative-channel"
    assert complete.headers["cache-control"] == "no-store"
    assert "answers" not in complete.text


@pytest.mark.anyio
async def test_api_rejects_invalid_and_oversized_answers_with_generic_errors(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    endpoint = "/api/v1/procedures/uidai-aadhaar-address-update/readiness/evaluate"
    caplog.set_level(logging.INFO)
    canary = "citizen-canary-value-9173"
    invalid_requests = [
        {"answers": {"mobile-auth-access": canary}},
        {"answers": {"unknown-question": canary}},
        {"answers": {}, "unexpected": canary},
        {"answers": {f"unknown-{index}": True for index in range(31)}},
    ]
    for body in invalid_requests:
        response = await client.post(endpoint, json=body)
        assert response.status_code == 422
        assert response.json() in ({"error": "Invalid request"}, {"error": "Invalid readiness answers"})
        assert canary not in response.text
        assert response.headers["cache-control"] == "no-store"
    assert canary not in caplog.text


@pytest.mark.anyio
async def test_readiness_unknown_service_error_is_generic(client: AsyncClient) -> None:
    response = await client.post("/api/v1/procedures/not-supported/readiness/evaluate", json={"answers": {}})
    assert response.status_code == 404
    assert response.json() == {"error": "Procedure not found"}

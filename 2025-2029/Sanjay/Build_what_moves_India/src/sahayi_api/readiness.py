from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, HttpUrl, StrictBool, StrictInt

from sahayi_api.procedures import (
    Identifier,
    LoadedProcedure,
    QuestionAnswerType,
    QuestionSensitivity,
    ReadinessOutcome,
    ReadinessQuestion,
    ReadinessStatus,
    RuleExpression,
    RuleOperator,
    ShortText,
    SourceId,
    SourceRecord,
    StrictModel,
    SupportedLocale,
    TranslationInfo,
    localized_sources,
    localized_text,
    translation_info,
)

MAX_ANSWERS = 30
MAX_EVALUATION_OPERATIONS = 256
AnswerValue = StrictBool | StrictInt | ShortText


class ReadinessInputError(ValueError):
    """A safe boundary error for invalid readiness answers."""


class ReadinessEvaluationRequest(StrictModel):
    answers: Annotated[dict[Identifier, AnswerValue], Field(max_length=MAX_ANSWERS)]


class ReadinessOptionResponse(StrictModel):
    option_id: Identifier
    label: ShortText


class ReadinessQuestionResponse(StrictModel):
    question_id: Identifier
    prompt: ShortText
    help_text: ShortText | None
    answer_type: QuestionAnswerType
    options: list[ReadinessOptionResponse] | None
    minimum: int | None
    maximum: int | None
    required: bool
    sensitivity: QuestionSensitivity


class ReadinessOutcomeResponse(StrictModel):
    outcome_id: Identifier
    status: ReadinessStatus
    title: ShortText
    explanation: str


class ReadinessTraceEntry(StrictModel):
    trace_type: Literal["question", "rule", "outcome", "default"]
    trace_id: Identifier
    source_ids: list[SourceId]


class ReadinessProgress(StrictModel):
    answered: int
    total: int


class ReadinessEvaluationResponse(StrictModel):
    locale: SupportedLocale
    translation: TranslationInfo
    pack_version: str
    pack_digest: str
    evaluation_status: Literal["incomplete"] | ReadinessStatus
    complete: bool
    progress: ReadinessProgress
    next_question: ReadinessQuestionResponse | None
    outcome: ReadinessOutcomeResponse | None
    reason_trace: list[ReadinessTraceEntry]
    sources: list[SourceRecord]
    recommended_next_steps: list[str]
    official_handoff_url: HttpUrl | None
    disclaimer: str


class OperationBudget:
    def __init__(self, limit: int = MAX_EVALUATION_OPERATIONS) -> None:
        self.limit = limit
        self.used = 0

    def consume(self) -> None:
        self.used += 1
        if self.used > self.limit:
            raise ReadinessInputError("Readiness evaluation budget exceeded")


def evaluate_expression(
    expression: RuleExpression,
    answers: dict[str, AnswerValue],
    budget: OperationBudget,
) -> bool:
    budget.consume()
    if expression.op is RuleOperator.ALL:
        return all(evaluate_expression(child, answers, budget) for child in expression.expressions or [])
    if expression.op is RuleOperator.ANY:
        return any(evaluate_expression(child, answers, budget) for child in expression.expressions or [])
    if expression.op is RuleOperator.NOT:
        return not evaluate_expression(expression.expression, answers, budget)  # type: ignore[arg-type]

    question_id = expression.question_id or ""
    if expression.op is RuleOperator.KNOWN:
        return question_id in answers
    if question_id not in answers:
        return False

    answer = answers[question_id]
    if expression.op is RuleOperator.EQUALS:
        return answer == expression.value and type(answer) is type(expression.value)
    if expression.op is RuleOperator.IN:
        return any(answer == item and type(answer) is type(item) for item in expression.values or [])
    if type(answer) is not int:
        return False
    comparison = expression.value
    if type(comparison) is not int:
        return False
    if expression.op is RuleOperator.LT:
        return answer < comparison
    if expression.op is RuleOperator.LTE:
        return answer <= comparison
    if expression.op is RuleOperator.GT:
        return answer > comparison
    if expression.op is RuleOperator.GTE:
        return answer >= comparison
    return False


def evaluate_readiness(
    loaded: LoadedProcedure,
    submitted_answers: dict[str, AnswerValue],
    *,
    locale: SupportedLocale = "en",
    operation_limit: int = MAX_EVALUATION_OPERATIONS,
) -> ReadinessEvaluationResponse:
    readiness = loaded.pack.readiness
    questions = {question.question_id: question for question in readiness.questions}
    unknown = set(submitted_answers) - questions.keys()
    if unknown:
        raise ReadinessInputError("Unknown readiness question")

    answers: dict[str, AnswerValue] = {}
    for question_id, value in submitted_answers.items():
        _validate_answer(questions[question_id], value)
        answers[question_id] = value

    budget = OperationBudget(operation_limit)
    visible_questions: list[ReadinessQuestion] = []
    for question in readiness.questions:
        visible = question.visible_when is None or evaluate_expression(question.visible_when, answers, budget)
        if not visible and question.question_id in answers:
            raise ReadinessInputError("Answer submitted for an inapplicable question")
        if visible:
            visible_questions.append(question)
    answered_visible = sum(question.question_id in answers for question in visible_questions)
    next_question = next((question for question in visible_questions if question.question_id not in answers), None)
    if next_question is not None:
        return _incomplete_response(loaded, next_question, answered_visible, len(visible_questions), locale)

    for rule in sorted(readiness.rules, key=lambda item: item.priority):
        if evaluate_expression(rule.expression, answers, budget):
            outcome = next(item for item in readiness.outcomes if item.outcome_id == rule.outcome_id)
            question_ids = _referenced_questions(rule.expression)
            trace = [
                ReadinessTraceEntry(trace_type="question", trace_id=question_id, source_ids=questions[question_id].source_ids)
                for question_id in question_ids
            ]
            trace.extend(
                [
                    ReadinessTraceEntry(trace_type="rule", trace_id=rule.rule_id, source_ids=rule.source_ids),
                    ReadinessTraceEntry(trace_type="outcome", trace_id=outcome.outcome_id, source_ids=outcome.source_ids),
                ]
            )
            return _complete_response(loaded, outcome, trace, answered_visible, len(visible_questions), locale)

    outcome = next(item for item in readiness.outcomes if item.is_default)
    trace = [
        ReadinessTraceEntry(trace_type="default", trace_id=outcome.outcome_id, source_ids=outcome.source_ids)
    ]
    return _complete_response(loaded, outcome, trace, answered_visible, len(visible_questions), locale)


def _validate_answer(question: ReadinessQuestion, value: AnswerValue) -> None:
    if question.answer_type is QuestionAnswerType.BOOLEAN:
        if type(value) is not bool:
            raise ReadinessInputError("Invalid readiness answer")
        return
    if question.answer_type is QuestionAnswerType.INTEGER:
        if type(value) is not int or value < question.minimum or value > question.maximum:  # type: ignore[operator]
            raise ReadinessInputError("Invalid readiness answer")
        return
    options = {option.option_id for option in question.options or []}
    if not isinstance(value, str) or value not in options:
        raise ReadinessInputError("Invalid readiness answer")


def _question_response(loaded: LoadedProcedure, question: ReadinessQuestion, locale: SupportedLocale) -> ReadinessQuestionResponse:
    pack = loaded.pack
    return ReadinessQuestionResponse(
        question_id=question.question_id,
        prompt=localized_text(pack, locale, f"question.{question.question_id}.prompt", question.prompt["en"]),
        help_text=localized_text(pack, locale, f"question.{question.question_id}.help", question.help_text["en"])
        if question.help_text
        else None,
        answer_type=question.answer_type,
        options=[
            ReadinessOptionResponse(
                option_id=option.option_id,
                label=localized_text(pack, locale, f"question.{question.question_id}.option.{option.option_id}", option.label["en"]),
            )
            for option in question.options
        ]
        if question.options
        else None,
        minimum=question.minimum,
        maximum=question.maximum,
        required=question.required,
        sensitivity=question.sensitivity,
    )


def _incomplete_response(
    loaded: LoadedProcedure,
    question: ReadinessQuestion,
    answered: int,
    total: int,
    locale: SupportedLocale,
) -> ReadinessEvaluationResponse:
    source_ids = set(question.source_ids)
    return ReadinessEvaluationResponse(
        locale=locale,
        translation=translation_info(loaded.pack, locale),
        pack_version=loaded.pack.pack_version,
        pack_digest=loaded.digest,
        evaluation_status="incomplete",
        complete=False,
        progress=ReadinessProgress(answered=answered, total=total),
        next_question=_question_response(loaded, question, locale),
        outcome=None,
        reason_trace=[ReadinessTraceEntry(trace_type="question", trace_id=question.question_id, source_ids=question.source_ids)],
        sources=_sources(loaded, source_ids, locale),
        recommended_next_steps=[],
        official_handoff_url=None,
        disclaimer=localized_text(
            loaded.pack,
            locale,
            "readiness.incomplete-disclaimer",
            "This readiness check stores no answers and does not make an eligibility decision.",
        ),
    )


def _complete_response(
    loaded: LoadedProcedure,
    outcome: ReadinessOutcome,
    trace: list[ReadinessTraceEntry],
    answered: int,
    total: int,
    locale: SupportedLocale,
) -> ReadinessEvaluationResponse:
    source_ids = {source_id for entry in trace for source_id in entry.source_ids}
    return ReadinessEvaluationResponse(
        locale=locale,
        translation=translation_info(loaded.pack, locale),
        pack_version=loaded.pack.pack_version,
        pack_digest=loaded.digest,
        evaluation_status=outcome.status,
        complete=True,
        progress=ReadinessProgress(answered=answered, total=total),
        next_question=None,
        outcome=ReadinessOutcomeResponse(
            outcome_id=outcome.outcome_id,
            status=outcome.status,
            title=localized_text(loaded.pack, locale, f"outcome.{outcome.outcome_id}.title", outcome.title["en"]),
            explanation=localized_text(
                loaded.pack, locale, f"outcome.{outcome.outcome_id}.explanation", outcome.explanation["en"]
            ),
        ),
        reason_trace=trace,
        sources=_sources(loaded, source_ids, locale),
        recommended_next_steps=[
            localized_text(loaded.pack, locale, f"outcome.{outcome.outcome_id}.next-step.{index}", step["en"])
            for index, step in enumerate(outcome.recommended_next_steps)
        ],
        official_handoff_url=outcome.official_handoff_url,
        disclaimer=localized_text(loaded.pack, locale, f"outcome.{outcome.outcome_id}.disclaimer", outcome.disclaimer["en"]),
    )


def _sources(loaded: LoadedProcedure, source_ids: set[str], locale: SupportedLocale) -> list[SourceRecord]:
    return localized_sources(loaded.pack, locale, source_ids)


def _referenced_questions(expression: RuleExpression) -> list[str]:
    if expression.op in {RuleOperator.ALL, RuleOperator.ANY}:
        references: list[str] = []
        for child in expression.expressions or []:
            for question_id in _referenced_questions(child):
                if question_id not in references:
                    references.append(question_id)
        return references
    if expression.op is RuleOperator.NOT:
        return _referenced_questions(expression.expression)  # type: ignore[arg-type]
    return [expression.question_id] if expression.question_id else []

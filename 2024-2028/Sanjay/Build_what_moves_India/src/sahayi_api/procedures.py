from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

from sahayi_api.privacy import contains_high_risk_pii

Identifier = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]
LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]
SourceId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)]
SourceIds = Annotated[list[SourceId], Field(min_length=1, max_length=12)]
LocalizedText = Annotated[dict[str, ShortText], Field(min_length=1, max_length=12)]
TranslationKey = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$", max_length=160)]
SupportedLocale = Literal["en", "hi", "ml"]
SUPPORTED_LOCALES = ("en", "hi", "ml")

_HTML = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
_REQUIRED_PROVENANCE = {
    "title",
    "short-description",
    "requirements",
    "required-documents",
    "fee",
    "steps",
    "submission-channels",
    "official-handoff-url",
    "limitations",
    "readiness",
}

MAX_RULE_DEPTH = 8
MAX_RULE_NODES = 128
MAX_RULE_LIST_SIZE = 16


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LifecycleStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class JurisdictionLevel(StrEnum):
    NATIONAL = "national"
    STATE = "state"
    LOCAL = "local"


class InteractionMode(StrEnum):
    ONLINE = "online"
    IN_PERSON = "in_person"


class SourceType(StrEnum):
    WEBPAGE = "webpage"
    PDF = "pdf"


class SourceNormalizationVersion(StrEnum):
    HTML_TEXT_V1 = "html-text-v1"
    PDF_BYTES_V1 = "pdf-bytes-v1"


class ExpectedSourceFormat(StrEnum):
    HTML = "html"
    PDF = "pdf"


class TrustState(StrEnum):
    CURRENT = "current"
    STALE = "stale"


class FeeVerificationStatus(StrEnum):
    CONFIRMED = "confirmed"
    CONFLICTING = "conflicting"
    FREE = "free"
    NOT_STATED = "not_stated"


class QuestionAnswerType(StrEnum):
    BOOLEAN = "boolean"
    SINGLE_CHOICE = "single_choice"
    INTEGER = "integer"


class QuestionSensitivity(StrEnum):
    NON_SENSITIVE = "non_sensitive"
    SENSITIVE = "sensitive"


class RuleOperator(StrEnum):
    ALL = "all"
    ANY = "any"
    NOT = "not"
    KNOWN = "known"
    EQUALS = "equals"
    IN = "in"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"


class ReadinessStatus(StrEnum):
    READY = "ready"
    ALTERNATIVE_PATH = "alternative_path"
    NEEDS_INFORMATION = "needs_information"
    CANNOT_CONFIRM = "cannot_confirm"


class TranslationMethod(StrEnum):
    CANONICAL_SOURCE = "canonical_source"
    MACHINE_ASSISTED_PROTOTYPE = "machine_assisted_prototype"


class TranslationReviewStatus(StrEnum):
    CANONICAL_VERIFIED = "canonical_verified"
    NATIVE_REVIEW_REQUIRED = "native_review_required"


class FormAssistanceMode(StrEnum):
    OFFICIAL_FORM_WORKSHEET = "official_form_worksheet"
    PREPARATION_WORKSHEET = "preparation_worksheet"


class FormFieldHandling(StrEnum):
    FICTIONAL_DEMO = "fictional_demo"
    CITIZEN_PRIVATE = "citizen_private"
    NOT_COLLECTED = "not_collected"


class FormFieldStatus(StrEnum):
    VERIFIED_OFFICIAL_FORM = "verified_official_form"
    PREPARATION_ONLY = "preparation_only"


class PreparationInputType(StrEnum):
    TEXT = "text"
    TEXTAREA = "textarea"
    SINGLE_CHOICE = "single_choice"
    READINESS_VALUE = "readiness_value"
    DOCUMENT_CLUE = "document_clue"
    NOT_COLLECTED = "not_collected"


class PreparationValidationKind(StrEnum):
    NON_EMPTY_TEXT = "non_empty_text"
    SINGLE_CHOICE = "single_choice"
    STRUCTURAL = "structural"
    NOT_COLLECTED = "not_collected"


class PreparationValueSource(StrEnum):
    CITIZEN_CONFIRMED_LOCAL_ANSWER = "citizen_confirmed_local_answer"
    CITIZEN_CONFIRMED_LOCAL_OCR = "citizen_confirmed_local_ocr_suggestion"
    DETERMINISTIC_DERIVED = "deterministic_derived_value"
    SYNTHETIC_DEMO = "bundled_synthetic_demonstration_profile"


class Jurisdiction(StrictModel):
    level: JurisdictionLevel
    name: ShortText


class SourceMonitoringPolicy(StrictModel):
    expected_format: ExpectedSourceFormat
    normalization_version: SourceNormalizationVersion
    reviewed_content_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None = None
    reviewed_fingerprint: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")] | None = None
    reviewed_at: datetime | None = None
    reviewed_size: Annotated[int, Field(ge=0, le=5_000_000)] | None = None
    reviewed_etag: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None
    reviewed_last_modified: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None
    allowed_redirect_hosts: Annotated[list[str], Field(default_factory=list, max_length=4)]
    max_bytes: Annotated[int, Field(ge=1024, le=5_000_000)] = 1_000_000

    @field_validator("reviewed_at")
    @classmethod
    def require_aware_review_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("reviewed_at must include a timezone")
        return value

    @field_validator("reviewed_etag", "reviewed_last_modified")
    @classmethod
    def reject_unsafe_header_values(cls, value: str | None) -> str | None:
        if value is not None and ("\r" in value or "\n" in value):
            raise ValueError("review metadata headers must be single-line")
        return value

    @field_validator("allowed_redirect_hosts")
    @classmethod
    def validate_redirect_hosts(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("allowed redirect hosts must be unique")
        for value in values:
            if value != value.lower() or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", value):
                raise ValueError("allowed redirect hosts must be lowercase DNS names")
            try:
                ipaddress.ip_address(value)
            except ValueError:
                pass
            else:
                raise ValueError("IP address redirect aliases are not permitted")
        return values

    @model_validator(mode="after")
    def validate_reviewed_baseline(self) -> SourceMonitoringPolicy:
        baseline_values = (self.reviewed_fingerprint, self.reviewed_at, self.reviewed_size, self.reviewed_content_type)
        if any(value is not None for value in baseline_values) and not all(value is not None for value in baseline_values):
            raise ValueError("reviewed fingerprint, timestamp, size, and content type must be supplied together")
        if self.reviewed_content_type is not None:
            media_type = self.reviewed_content_type.split(";", 1)[0].strip().lower()
            accepted = {"application/pdf"} if self.expected_format is ExpectedSourceFormat.PDF else {"text/html", "application/xhtml+xml"}
            if media_type not in accepted:
                raise ValueError("reviewed content type must match the expected source format")
        if self.expected_format is ExpectedSourceFormat.HTML and self.normalization_version is not SourceNormalizationVersion.HTML_TEXT_V1:
            raise ValueError("HTML sources require html-text-v1 normalization")
        if self.expected_format is ExpectedSourceFormat.PDF and self.normalization_version is not SourceNormalizationVersion.PDF_BYTES_V1:
            raise ValueError("PDF sources require pdf-bytes-v1 normalization")
        return self


class SourceRecord(StrictModel):
    source_id: SourceId
    publisher: ShortText
    title: ShortText
    url: HttpUrl
    retrieved_at: datetime
    official_updated_date: date | None = None
    sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")] | None = None
    source_type: SourceType
    monitoring: SourceMonitoringPolicy | None = None

    @field_validator("url")
    @classmethod
    def require_https(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("official source URLs must use HTTPS")
        if value.username is not None or value.password is not None:
            raise ValueError("official source URLs must not include credentials")
        try:
            ipaddress.ip_address(value.host)
        except ValueError:
            pass
        else:
            raise ValueError("official source URLs must use public DNS names, not IP addresses")
        return value

    @field_validator("retrieved_at")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_monitoring_policy(self) -> SourceRecord:
        if self.monitoring is None:
            return self
        expected = ExpectedSourceFormat.PDF if self.source_type is SourceType.PDF else ExpectedSourceFormat.HTML
        if self.monitoring.expected_format is not expected:
            raise ValueError("monitoring format must match the source type")
        return self


class CitedFact(StrictModel):
    fact_id: Identifier
    text: LongText
    source_ids: SourceIds


class PreparationChoice(StrictModel):
    option_id: Identifier
    label: LocalizedText

    @field_validator("label")
    @classmethod
    def require_complete_locales(cls, value: dict[str, str]) -> dict[str, str]:
        _validate_localized_text(value)
        if set(value) != set(SUPPORTED_LOCALES):
            raise ValueError("preparation choices must contain exactly en, hi, and ml")
        return value


class PreparationValidationRule(StrictModel):
    kind: PreparationValidationKind
    minimum_length: Annotated[int, Field(ge=1, le=400)] | None = None
    maximum_length: Annotated[int, Field(ge=1, le=400)] | None = None

    @model_validator(mode="after")
    def validate_lengths(self) -> PreparationValidationRule:
        if self.kind is PreparationValidationKind.NON_EMPTY_TEXT:
            if self.minimum_length is None or self.maximum_length is None or self.minimum_length > self.maximum_length:
                raise ValueError("text validation requires an ordered minimum and maximum length")
        elif self.minimum_length is not None or self.maximum_length is not None:
            raise ValueError("only text validation may define length bounds")
        return self


class FormAssistanceField(StrictModel):
    field_id: Identifier
    label: LocalizedText
    explanation: LocalizedText
    demo_value: LocalizedText | None = None
    handling: FormFieldHandling
    status: FormFieldStatus
    source_ids: SourceIds
    question_id: Identifier | None = None
    question: LocalizedText | None = None
    why_needed: LocalizedText | None = None
    input_type: PreparationInputType | None = None
    required: bool | None = None
    validation: PreparationValidationRule | None = None
    supported_value_sources: Annotated[list[PreparationValueSource], Field(default_factory=list, max_length=4)]
    may_appear_on_sheet: bool | None = None
    confirmation_required: bool | None = None
    editable: bool | None = None
    choices: Annotated[list[PreparationChoice], Field(default_factory=list, max_length=12)]
    readiness_question_id: Identifier | None = None
    document_ids: Annotated[list[Identifier], Field(default_factory=list, max_length=8)]

    @field_validator("label", "explanation", "demo_value", "question", "why_needed")
    @classmethod
    def require_complete_locales(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        _validate_localized_text(value)
        if set(value) != set(SUPPORTED_LOCALES):
            raise ValueError("form assistance text must contain exactly en, hi, and ml")
        return value

    @model_validator(mode="after")
    def validate_handling(self) -> FormAssistanceField:
        if self.handling is FormFieldHandling.FICTIONAL_DEMO and self.demo_value is None:
            raise ValueError("fictional demo fields require a demo value")
        if self.handling is not FormFieldHandling.FICTIONAL_DEMO and self.demo_value is not None:
            raise ValueError("private and uncollected fields must not contain demo values")
        if self.demo_value is not None and any(contains_high_risk_pii(value) for value in self.demo_value.values()):
            raise ValueError("fictional demo values must not contain identifier-shaped data")
        if self.input_type is PreparationInputType.SINGLE_CHOICE and not self.choices:
            raise ValueError("single-choice preparation fields require choices")
        if self.input_type is not None and self.input_type is not PreparationInputType.SINGLE_CHOICE and self.choices:
            raise ValueError("only single-choice preparation fields may define choices")
        if self.input_type is PreparationInputType.READINESS_VALUE and self.readiness_question_id is None:
            raise ValueError("readiness-derived preparation fields require a readiness question")
        if self.input_type is not None and self.input_type is not PreparationInputType.READINESS_VALUE and self.readiness_question_id is not None:
            raise ValueError("only readiness-derived fields may reference a readiness question")
        if self.input_type is PreparationInputType.DOCUMENT_CLUE and not self.document_ids:
            raise ValueError("document-clue preparation fields require document IDs")
        if self.input_type is not None and self.input_type is not PreparationInputType.DOCUMENT_CLUE and self.document_ids:
            raise ValueError("only document-clue fields may reference document IDs")
        return self

    def has_complete_preparation_contract(self) -> bool:
        return all(value is not None for value in (
            self.question_id,
            self.question,
            self.why_needed,
            self.input_type,
            self.required,
            self.validation,
            self.may_appear_on_sheet,
            self.confirmation_required,
            self.editable,
        )) and (bool(self.supported_value_sources) or self.input_type is PreparationInputType.NOT_COLLECTED)


class SyntheticPersona(StrictModel):
    persona_id: Identifier
    display_name: LocalizedText
    synthetic: Literal[True]
    field_ids: Annotated[list[Identifier], Field(default_factory=list, max_length=20)]
    readiness_answers: Annotated[dict[Identifier, StrictBool | StrictInt | ShortText], Field(min_length=1, max_length=30)]

    @field_validator("display_name")
    @classmethod
    def require_complete_locales(cls, value: dict[str, str]) -> dict[str, str]:
        _validate_localized_text(value)
        if set(value) != set(SUPPORTED_LOCALES):
            raise ValueError("persona text must contain exactly en, hi, and ml")
        return value


class AssistanceDefinition(StrictModel):
    form_mode: FormAssistanceMode
    title: LocalizedText
    form_source_ids: Annotated[list[SourceId], Field(default_factory=list, max_length=4)]
    preparation_fields: Annotated[list[FormAssistanceField], Field(min_length=1, max_length=30)]
    personas: Annotated[list[SyntheticPersona], Field(min_length=1, max_length=8)]

    @field_validator("title")
    @classmethod
    def require_complete_locales(cls, value: dict[str, str]) -> dict[str, str]:
        _validate_localized_text(value)
        if set(value) != set(SUPPORTED_LOCALES):
            raise ValueError("assistance title must contain exactly en, hi, and ml")
        return value

    @model_validator(mode="after")
    def validate_definition(self) -> AssistanceDefinition:
        _require_unique([field.field_id for field in self.preparation_fields], "form assistance field IDs")
        _require_unique([field.question_id for field in self.preparation_fields if field.question_id is not None], "preparation question IDs")
        _require_unique([persona.persona_id for persona in self.personas], "synthetic persona IDs")
        known_fields = {field.field_id for field in self.preparation_fields}
        demo_fields = {field.field_id for field in self.preparation_fields if field.handling is FormFieldHandling.FICTIONAL_DEMO}
        for persona in self.personas:
            if not set(persona.field_ids) <= known_fields:
                raise ValueError("synthetic persona references an unknown form field")
            if not set(persona.field_ids) <= demo_fields:
                raise ValueError("synthetic personas may reference only fictional demo fields")
        if self.form_mode is FormAssistanceMode.OFFICIAL_FORM_WORKSHEET and not self.form_source_ids:
            raise ValueError("official form worksheet requires an official form source")
        return self


class DocumentGuidance(StrictModel):
    document_id: Identifier
    name: ShortText
    guidance: LongText
    source_ids: SourceIds


class FeeClaim(StrictModel):
    amount: Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    qualifier: ShortText
    source_ids: SourceIds


class FeeInformation(StrictModel):
    verification_status: FeeVerificationStatus
    amount: Annotated[Decimal, Field(ge=0, max_digits=10, decimal_places=2)] | None
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] | None
    display_message: ShortText
    claims: Annotated[list[FeeClaim], Field(max_length=8)]
    resolution_guidance: ShortText | None = None
    source_ids: SourceIds

    @model_validator(mode="after")
    def validate_status(self) -> FeeInformation:
        status = self.verification_status
        claim_values = {(claim.amount, claim.currency) for claim in self.claims}
        claim_sources = {source_id for claim in self.claims for source_id in claim.source_ids}

        if status is FeeVerificationStatus.CONFIRMED:
            if self.amount is None or self.currency is None or not self.claims:
                raise ValueError("confirmed fee requires a canonical amount, currency, and at least one claim")
            if self.amount == 0:
                raise ValueError("a zero fee must use free verification status")
            if claim_values != {(self.amount, self.currency)}:
                raise ValueError("confirmed fee claims must agree with the canonical amount and currency")
        elif status is FeeVerificationStatus.CONFLICTING:
            if self.amount is not None or self.currency is not None:
                raise ValueError("conflicting fee must not expose a canonical amount or currency")
            if len(self.claims) < 2 or len(claim_values) < 2:
                raise ValueError("conflicting fee requires at least two distinct claims with different values")
            if self.resolution_guidance is None:
                raise ValueError("conflicting fee requires resolution guidance")
        elif status is FeeVerificationStatus.FREE:
            if self.amount != 0 or self.currency is None or not self.claims:
                raise ValueError("free fee requires a zero canonical amount, currency, and at least one claim")
            if claim_values != {(Decimal("0"), self.currency)}:
                raise ValueError("free fee claims must state zero in the canonical currency")
        elif self.amount is not None or self.currency is not None or self.claims:
            raise ValueError("not_stated fee must not include an amount, currency, or claims")

        if self.claims and claim_sources != set(self.source_ids):
            raise ValueError("fee source_ids must match the sources referenced by its claims")
        return self


class ProcedureStep(StrictModel):
    step_id: Identifier
    order: Annotated[int, Field(ge=1, le=50)]
    title: ShortText
    instruction: LongText
    source_ids: SourceIds


class SubmissionChannel(StrictModel):
    channel_id: Identifier
    mode: InteractionMode
    name: ShortText
    guidance: LongText
    source_ids: SourceIds


class RuleExpression(StrictModel):
    op: RuleOperator
    expressions: Annotated[list[RuleExpression], Field(min_length=1, max_length=MAX_RULE_LIST_SIZE)] | None = None
    expression: RuleExpression | None = None
    question_id: Identifier | None = None
    value: StrictBool | StrictInt | ShortText | None = None
    values: Annotated[list[StrictBool | StrictInt | ShortText], Field(min_length=1, max_length=MAX_RULE_LIST_SIZE)] | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> RuleExpression:
        allowed = {
            RuleOperator.ALL: {"op", "expressions"},
            RuleOperator.ANY: {"op", "expressions"},
            RuleOperator.NOT: {"op", "expression"},
            RuleOperator.KNOWN: {"op", "question_id"},
            RuleOperator.EQUALS: {"op", "question_id", "value"},
            RuleOperator.IN: {"op", "question_id", "values"},
            RuleOperator.LT: {"op", "question_id", "value"},
            RuleOperator.LTE: {"op", "question_id", "value"},
            RuleOperator.GT: {"op", "question_id", "value"},
            RuleOperator.GTE: {"op", "question_id", "value"},
        }[self.op]
        supplied = self.model_fields_set
        if supplied != allowed:
            raise ValueError(f"{self.op} expression requires exactly: {', '.join(sorted(allowed))}")
        return self


class ReadinessOption(StrictModel):
    option_id: Identifier
    label: LocalizedText

    @field_validator("label")
    @classmethod
    def require_english_label(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_localized_text(value)


class ReadinessQuestion(StrictModel):
    question_id: Identifier
    prompt: LocalizedText
    help_text: LocalizedText | None = None
    answer_type: QuestionAnswerType
    options: Annotated[list[ReadinessOption], Field(min_length=2, max_length=12)] | None = None
    minimum: Annotated[StrictInt, Field(ge=-1000, le=1000)] | None = None
    maximum: Annotated[StrictInt, Field(ge=-1000, le=1000)] | None = None
    required: StrictBool
    sensitivity: QuestionSensitivity
    source_ids: SourceIds
    visible_when: RuleExpression | None = None

    @field_validator("prompt", "help_text")
    @classmethod
    def require_english_text(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        return _validate_localized_text(value) if value is not None else None

    @model_validator(mode="after")
    def validate_answer_contract(self) -> ReadinessQuestion:
        if self.answer_type is QuestionAnswerType.SINGLE_CHOICE:
            if self.options is None or self.minimum is not None or self.maximum is not None:
                raise ValueError("single_choice questions require options and no numeric bounds")
            option_ids = [option.option_id for option in self.options]
            if len(option_ids) != len(set(option_ids)):
                raise ValueError("question option IDs must be unique")
        elif self.answer_type is QuestionAnswerType.INTEGER:
            if self.options is not None or self.minimum is None or self.maximum is None:
                raise ValueError("integer questions require numeric bounds and no options")
            if self.minimum > self.maximum:
                raise ValueError("integer question minimum must not exceed maximum")
        elif self.options is not None or self.minimum is not None or self.maximum is not None:
            raise ValueError("boolean questions cannot define options or numeric bounds")
        return self


class ReadinessOutcome(StrictModel):
    outcome_id: Identifier
    status: ReadinessStatus
    title: LocalizedText
    explanation: LocalizedText
    recommended_next_steps: Annotated[list[LocalizedText], Field(min_length=1, max_length=12)]
    official_handoff_url: HttpUrl
    source_ids: SourceIds
    disclaimer: LocalizedText
    is_default: StrictBool = False

    @field_validator("title", "explanation", "disclaimer")
    @classmethod
    def require_english_text(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_localized_text(value)

    @field_validator("recommended_next_steps")
    @classmethod
    def require_english_steps(cls, value: list[dict[str, str]]) -> list[dict[str, str]]:
        return [_validate_localized_text(item) for item in value]

    @field_validator("official_handoff_url")
    @classmethod
    def require_https_handoff(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("official handoff URL must use HTTPS")
        return value


class ReadinessRule(StrictModel):
    rule_id: Identifier
    priority: Annotated[StrictInt, Field(ge=1, le=10000)]
    expression: RuleExpression
    outcome_id: Identifier
    source_ids: SourceIds


class ReadinessDefinition(StrictModel):
    questions: Annotated[list[ReadinessQuestion], Field(min_length=1, max_length=30)]
    additional_review_items: Annotated[list[CitedFact], Field(default_factory=list, max_length=20)]
    outcomes: Annotated[list[ReadinessOutcome], Field(min_length=2, max_length=30)]
    rules: Annotated[list[ReadinessRule], Field(min_length=1, max_length=60)]

    @model_validator(mode="after")
    def validate_definition(self) -> ReadinessDefinition:
        _require_unique([question.question_id for question in self.questions], "question IDs")
        _require_unique([outcome.outcome_id for outcome in self.outcomes], "outcome IDs")
        _require_unique([rule.rule_id for rule in self.rules], "rule IDs")
        _require_unique([rule.priority for rule in self.rules], "rule priorities")

        defaults = [outcome for outcome in self.outcomes if outcome.is_default]
        if len(defaults) != 1 or defaults[0].status is not ReadinessStatus.NEEDS_INFORMATION:
            raise ValueError("readiness requires exactly one needs_information default outcome")

        questions = {question.question_id: question for question in self.questions}
        outcomes = {outcome.outcome_id for outcome in self.outcomes}
        earlier: set[str] = set()
        total_nodes = 0
        for question in self.questions:
            if question.visible_when is not None:
                nodes, referenced = _validate_expression(question.visible_when, questions)
                total_nodes += nodes
                if not referenced <= earlier:
                    raise ValueError("question visibility may reference only earlier questions")
            earlier.add(question.question_id)
        for rule in self.rules:
            if rule.outcome_id not in outcomes:
                raise ValueError(f"unknown outcome reference: {rule.outcome_id}")
            nodes, _ = _validate_expression(rule.expression, questions)
            total_nodes += nodes
        if total_nodes > MAX_RULE_NODES:
            raise ValueError(f"readiness expressions exceed {MAX_RULE_NODES} total nodes")
        return self


class LocaleTranslationMetadata(StrictModel):
    method: TranslationMethod
    review_status: TranslationReviewStatus
    disclaimer: LongText


class LocaleTranslation(StrictModel):
    intent_phrases: Annotated[list[ShortText], Field(min_length=1, max_length=30)]
    text: Annotated[dict[TranslationKey, LongText], Field(min_length=1, max_length=500)]


class PackLocalization(StrictModel):
    canonical_locale: Literal["en"]
    locale_metadata: dict[SupportedLocale, LocaleTranslationMetadata]
    translations: dict[Literal["hi", "ml"], LocaleTranslation]

    @model_validator(mode="after")
    def validate_locale_contract(self) -> PackLocalization:
        if set(self.locale_metadata) != set(SUPPORTED_LOCALES):
            raise ValueError("locale metadata must contain exactly en, hi, and ml")
        if set(self.translations) != {"hi", "ml"}:
            raise ValueError("translations must contain exactly hi and ml")
        english = self.locale_metadata["en"]
        if english.method is not TranslationMethod.CANONICAL_SOURCE or english.review_status is not TranslationReviewStatus.CANONICAL_VERIFIED:
            raise ValueError("English locale metadata must identify canonical verified source text")
        for locale in ("hi", "ml"):
            metadata = self.locale_metadata[locale]
            if metadata.method is not TranslationMethod.MACHINE_ASSISTED_PROTOTYPE or metadata.review_status is not TranslationReviewStatus.NATIVE_REVIEW_REQUIRED:
                raise ValueError("Hindi and Malayalam must be marked as machine-assisted prototypes requiring native review")
        return self


def _validate_localized_text(value: dict[str, str]) -> dict[str, str]:
    if "en" not in value:
        raise ValueError("English content is required")
    if any(not re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", locale) for locale in value):
        raise ValueError("invalid locale key")
    return value


def _require_unique(values: list[Any], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _validate_expression(
    expression: RuleExpression,
    questions: dict[str, ReadinessQuestion],
    depth: int = 1,
) -> tuple[int, set[str]]:
    if depth > MAX_RULE_DEPTH:
        raise ValueError(f"rule expression exceeds maximum depth {MAX_RULE_DEPTH}")
    if expression.op in {RuleOperator.ALL, RuleOperator.ANY}:
        nodes, references = 1, set()
        for child in expression.expressions or []:
            child_nodes, child_references = _validate_expression(child, questions, depth + 1)
            nodes += child_nodes
            references.update(child_references)
        return nodes, references
    if expression.op is RuleOperator.NOT:
        child_nodes, references = _validate_expression(expression.expression, questions, depth + 1)  # type: ignore[arg-type]
        return child_nodes + 1, references

    question = questions.get(expression.question_id or "")
    if question is None:
        raise ValueError(f"unknown question reference: {expression.question_id}")
    value = expression.value
    if expression.op is RuleOperator.IN:
        if question.answer_type is not QuestionAnswerType.SINGLE_CHOICE:
            raise ValueError("in operator requires a single_choice question")
        valid_options = {option.option_id for option in question.options or []}
        if any(not isinstance(item, str) or item not in valid_options for item in expression.values or []):
            raise ValueError("in operator contains an invalid option")
    elif expression.op in {RuleOperator.LT, RuleOperator.LTE, RuleOperator.GT, RuleOperator.GTE}:
        if question.answer_type is not QuestionAnswerType.INTEGER or type(value) is not int:
            raise ValueError("comparison operators require an integer question and integer value")
    elif expression.op is RuleOperator.EQUALS:
        if question.answer_type is QuestionAnswerType.BOOLEAN and type(value) is not bool:
            raise ValueError("boolean equals requires a boolean value")
        if question.answer_type is QuestionAnswerType.INTEGER and type(value) is not int:
            raise ValueError("integer equals requires an integer value")
        if question.answer_type is QuestionAnswerType.SINGLE_CHOICE:
            valid_options = {option.option_id for option in question.options or []}
            if not isinstance(value, str) or value not in valid_options:
                raise ValueError("single_choice equals requires a valid option")
    return 1, {question.question_id}


class ProcedurePack(StrictModel):
    schema_version: Literal["1.0"]
    service_id: Identifier
    pack_version: Annotated[str, StringConstraints(pattern=r"^[1-9]\d*\.\d+\.\d+$", max_length=32)]
    status: LifecycleStatus
    jurisdiction: Jurisdiction
    department: ShortText
    publisher: ShortText
    title: Annotated[dict[str, ShortText], Field(min_length=1, max_length=12)]
    short_description: Annotated[dict[str, ShortText], Field(min_length=1, max_length=12)]
    intent_phrases: Annotated[list[ShortText], Field(min_length=1, max_length=30)]
    category: Identifier
    interaction_modes: Annotated[list[InteractionMode], Field(min_length=1, max_length=4)]
    sources: Annotated[list[SourceRecord], Field(min_length=1, max_length=30)]
    last_verified_at: datetime
    review_due_at: datetime
    requirements: Annotated[list[CitedFact], Field(min_length=1, max_length=30)]
    required_documents: Annotated[list[DocumentGuidance], Field(min_length=1, max_length=30)]
    fee: FeeInformation
    steps: Annotated[list[ProcedureStep], Field(min_length=1, max_length=50)]
    submission_channels: Annotated[list[SubmissionChannel], Field(min_length=1, max_length=8)]
    official_handoff_url: HttpUrl
    tracking_guidance: CitedFact | None = None
    limitations: Annotated[list[CitedFact], Field(min_length=1, max_length=20)]
    readiness: ReadinessDefinition
    assistance: AssistanceDefinition | None = None
    localization: PackLocalization | None = None
    provenance: Annotated[dict[Identifier, SourceIds], Field(min_length=1, max_length=100)]

    @field_validator("title", "short_description")
    @classmethod
    def require_english(cls, value: dict[str, str]) -> dict[str, str]:
        if "en" not in value:
            raise ValueError("English content is required")
        if any(not re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", locale) for locale in value):
            raise ValueError("invalid locale key")
        return value

    @field_validator("last_verified_at", "review_due_at")
    @classmethod
    def require_aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("verification timestamps must include a timezone")
        return value

    @field_validator("official_handoff_url")
    @classmethod
    def require_https_handoff(cls, value: HttpUrl) -> HttpUrl:
        if value.scheme != "https":
            raise ValueError("official handoff URL must use HTTPS")
        return value

    @model_validator(mode="after")
    def validate_pack(self) -> ProcedurePack:
        if self.review_due_at <= self.last_verified_at:
            raise ValueError("review_due_at must be after last_verified_at")

        orders = [step.order for step in self.steps]
        if orders != list(range(1, len(orders) + 1)):
            raise ValueError("steps must be ordered consecutively from 1")

        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source IDs must be unique")
        known_sources = set(source_ids)

        references: list[str] = []
        for item in [*self.requirements, *self.required_documents, self.fee, *self.fee.claims, *self.steps, *self.submission_channels, *self.limitations, *self.readiness.questions, *self.readiness.additional_review_items, *self.readiness.outcomes, *self.readiness.rules]:
            references.extend(item.source_ids)
        if self.assistance is not None:
            references.extend(self.assistance.form_source_ids)
            for field in self.assistance.preparation_fields:
                references.extend(field.source_ids)
            if self.status is LifecycleStatus.ACTIVE and any(not field.has_complete_preparation_contract() for field in self.assistance.preparation_fields):
                raise ValueError("active pack preparation fields require the complete preparation contract")
            questions = {question.question_id: question for question in self.readiness.questions}
            documents = {document.document_id for document in self.required_documents}
            for field in self.assistance.preparation_fields:
                if field.readiness_question_id is not None and field.readiness_question_id not in questions:
                    raise ValueError("preparation field references an unknown readiness question")
                if not set(field.document_ids) <= documents:
                    raise ValueError("preparation field references an unknown document")
            for persona in self.assistance.personas:
                if not set(persona.readiness_answers) <= questions.keys():
                    raise ValueError("synthetic persona references an unknown readiness question")
                for question_id, value in persona.readiness_answers.items():
                    question = questions[question_id]
                    if question.answer_type is QuestionAnswerType.BOOLEAN and type(value) is not bool:
                        raise ValueError("synthetic persona has an invalid boolean readiness answer")
                    if question.answer_type is QuestionAnswerType.INTEGER and type(value) is not int:
                        raise ValueError("synthetic persona has an invalid integer readiness answer")
                    if question.answer_type is QuestionAnswerType.SINGLE_CHOICE:
                        options = {option.option_id for option in question.options or []}
                        if not isinstance(value, str) or value not in options:
                            raise ValueError("synthetic persona has an invalid choice readiness answer")
            if self.assistance.form_mode is FormAssistanceMode.OFFICIAL_FORM_WORKSHEET:
                sources_by_id = {source.source_id: source for source in self.sources}
                if any(sources_by_id[source_id].source_type is not SourceType.PDF for source_id in self.assistance.form_source_ids):
                    raise ValueError("official form worksheet sources must be PDF sources")
                if any(field.status is not FormFieldStatus.VERIFIED_OFFICIAL_FORM for field in self.assistance.preparation_fields):
                    raise ValueError("official form worksheet fields must be verified against the official form")
            elif self.assistance.form_source_ids:
                raise ValueError("preparation worksheets must not claim an official form source")
        if self.tracking_guidance:
            references.extend(self.tracking_guidance.source_ids)
        for mapped_sources in self.provenance.values():
            references.extend(mapped_sources)
        missing = sorted(set(references) - known_sources)
        if missing:
            raise ValueError(f"unknown source references: {', '.join(missing)}")
        monitored_unreferenced = sorted(
            source.source_id for source in self.sources if source.monitoring is not None and source.source_id not in references
        )
        if monitored_unreferenced:
            raise ValueError(f"monitoring configured for unreferenced sources: {', '.join(monitored_unreferenced)}")
        required_provenance = _REQUIRED_PROVENANCE | ({"tracking-guidance"} if self.tracking_guidance else set())
        unmapped = sorted(required_provenance - self.provenance.keys())
        if unmapped:
            raise ValueError(f"missing provenance mappings: {', '.join(unmapped)}")

        if self.status is LifecycleStatus.ACTIVE:
            if self.localization is None:
                raise ValueError("active procedure packs require complete localization")
            required_keys = required_translation_keys(self)
            for locale, translation in self.localization.translations.items():
                supplied_keys = set(translation.text)
                missing_keys = sorted(required_keys - supplied_keys)
                unexpected_keys = sorted(supplied_keys - required_keys)
                if missing_keys or unexpected_keys:
                    detail = []
                    if missing_keys:
                        detail.append(f"missing {locale} translation keys: {', '.join(missing_keys)}")
                    if unexpected_keys:
                        detail.append(f"unexpected {locale} translation keys: {', '.join(unexpected_keys)}")
                    raise ValueError("; ".join(detail))

        self._reject_html(self.model_dump(mode="json"))
        return self

    @classmethod
    def _reject_html(cls, value: object) -> None:
        if isinstance(value, str) and _HTML.search(value):
            raise ValueError("HTML content is not permitted")
        if isinstance(value, dict):
            for key, nested in value.items():
                cls._reject_html(key)
                cls._reject_html(nested)
        elif isinstance(value, list):
            for nested in value:
                cls._reject_html(nested)


def required_translation_keys(pack: ProcedurePack) -> set[str]:
    keys = {"title", "short-description", "category-label", "readiness.incomplete-disclaimer"}
    keys.update(f"source.{item.source_id}.title" for item in pack.sources)
    keys.update(f"requirement.{item.fact_id}" for item in pack.requirements)
    for item in pack.required_documents:
        keys.update({f"document.{item.document_id}.name", f"document.{item.document_id}.guidance"})
    keys.add("fee.display-message")
    keys.update(f"fee.claim.{index}.qualifier" for index, _ in enumerate(pack.fee.claims))
    if pack.fee.resolution_guidance is not None:
        keys.add("fee.resolution-guidance")
    for item in pack.steps:
        keys.update({f"step.{item.step_id}.title", f"step.{item.step_id}.instruction"})
    for item in pack.submission_channels:
        keys.update({f"channel.{item.channel_id}.name", f"channel.{item.channel_id}.guidance"})
    if pack.tracking_guidance is not None:
        keys.add("tracking-guidance")
    keys.update(f"limitation.{item.fact_id}" for item in pack.limitations)
    keys.update(f"additional-review.{item.fact_id}" for item in pack.readiness.additional_review_items)
    for question in pack.readiness.questions:
        keys.add(f"question.{question.question_id}.prompt")
        if question.help_text is not None:
            keys.add(f"question.{question.question_id}.help")
        keys.update(f"question.{question.question_id}.option.{option.option_id}" for option in question.options or [])
    for outcome in pack.readiness.outcomes:
        keys.update(
            {
                f"outcome.{outcome.outcome_id}.title",
                f"outcome.{outcome.outcome_id}.explanation",
                f"outcome.{outcome.outcome_id}.disclaimer",
            }
        )
        keys.update(f"outcome.{outcome.outcome_id}.next-step.{index}" for index, _ in enumerate(outcome.recommended_next_steps))
    return keys


def localized_text(pack: ProcedurePack, locale: SupportedLocale, key: str, english: str) -> str:
    if locale == "en":
        return english
    if pack.localization is None:
        return english
    return pack.localization.translations[locale].text[key]


class TranslationInfo(StrictModel):
    locale: SupportedLocale
    canonical_locale: Literal["en"]
    method: TranslationMethod
    review_status: TranslationReviewStatus
    disclaimer: str


def translation_info(pack: ProcedurePack, locale: SupportedLocale) -> TranslationInfo:
    if pack.localization is None:
        return TranslationInfo(
            locale="en",
            canonical_locale="en",
            method=TranslationMethod.CANONICAL_SOURCE,
            review_status=TranslationReviewStatus.CANONICAL_VERIFIED,
            disclaimer="English is the canonical verified guidance. Official source wording prevails.",
        )
    metadata = pack.localization.locale_metadata[locale]
    return TranslationInfo(locale=locale, canonical_locale="en", **metadata.model_dump())


class PackLoadError(RuntimeError):
    """Safe boundary error for invalid or unavailable procedure packs."""


class LoadedProcedure(StrictModel):
    pack: ProcedurePack
    digest: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]

    def trust_state(self, now: datetime | None = None) -> TrustState:
        current_time = now or datetime.now(UTC)
        if current_time.tzinfo is None or current_time.utcoffset() is None:
            raise ValueError("current time must include a timezone")
        return TrustState.STALE if current_time > self.pack.review_due_at else TrustState.CURRENT


def pack_digest(pack: ProcedurePack) -> str:
    payload = pack.model_dump(mode="json")
    # Preserve v1 digest compatibility for packs that do not use the later,
    # optional additional-review guidance.
    if not payload["readiness"]["additional_review_items"]:
        del payload["readiness"]["additional_review_items"]
    if payload["assistance"] is None:
        del payload["assistance"]
    for source in payload["sources"]:
        if source["monitoring"] is None:
            del source["monitoring"]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_procedure_registry(pack_root: Path) -> dict[str, LoadedProcedure]:
    try:
        paths = sorted(pack_root.glob("**/*.json"))
        packs = [ProcedurePack.model_validate_json(path.read_text(encoding="utf-8")) for path in paths]
    except (OSError, ValueError) as exc:
        raise PackLoadError("Procedure packs are unavailable") from exc

    versions: set[tuple[str, str]] = set()
    active_by_service: dict[str, list[ProcedurePack]] = {}
    for pack in packs:
        version_key = (pack.service_id, pack.pack_version)
        if version_key in versions:
            raise PackLoadError("Duplicate procedure pack version")
        versions.add(version_key)
        if pack.status is LifecycleStatus.ACTIVE:
            active_by_service.setdefault(pack.service_id, []).append(pack)

    if not active_by_service:
        raise PackLoadError("No active procedure packs are available")
    if any(len(active) != 1 for active in active_by_service.values()):
        raise PackLoadError("A service must have exactly one active procedure pack")

    return {
        service_id: LoadedProcedure(pack=active[0], digest=pack_digest(active[0]))
        for service_id, active in active_by_service.items()
    }


def default_pack_root() -> Path:
    return Path(__file__).resolve().parents[2] / "procedure-packs" / "packs"


class ProcedureSummary(StrictModel):
    """The intentionally small, browser-safe catalogue used for local matching."""

    service_id: Identifier
    title: ShortText
    short_description: ShortText
    intent_phrases: Annotated[list[ShortText], Field(min_length=1, max_length=30)]
    category: Identifier
    category_label: ShortText
    trust_state: TrustState
    attention_required: bool


class ProcedureListResponse(StrictModel):
    locale: SupportedLocale
    translation: TranslationInfo
    procedures: list[ProcedureSummary]


class MonitoringTrustInfo(StrictModel):
    prototype_available: bool
    continuous_monitoring: Literal[False]
    baseline_status: Literal["reviewed", "review_required", "unavailable"]
    human_review_required: Literal[True]
    monitored_source_count: Annotated[int, Field(ge=0, le=30)]


class ProcedureDetail(StrictModel):
    locale: SupportedLocale
    translation: TranslationInfo
    service_id: Identifier
    title: ShortText
    short_description: ShortText
    category: Identifier
    category_label: ShortText
    jurisdiction: Jurisdiction
    department: ShortText
    official_publisher: ShortText
    interaction_modes: list[InteractionMode]
    requirements: list[CitedFact]
    required_documents: list[DocumentGuidance]
    fee: FeeInformation
    steps: list[ProcedureStep]
    submission_channels: list[SubmissionChannel]
    official_handoff_url: HttpUrl
    tracking_guidance: CitedFact | None
    sources: list[SourceRecord]
    provenance: dict[str, list[str]]
    pack_version: str
    pack_digest: str
    last_verified_at: datetime
    review_due_at: datetime
    trust_state: TrustState
    attention_required: bool
    monitoring: MonitoringTrustInfo
    limitations: list[CitedFact]
    additional_review_items: list[CitedFact]


def fee_attention_required(fee: FeeInformation) -> bool:
    return fee.verification_status is FeeVerificationStatus.CONFLICTING


def summarize_procedure(
    loaded: LoadedProcedure,
    now: datetime | None = None,
    locale: SupportedLocale = "en",
) -> ProcedureSummary:
    pack = loaded.pack
    intent_phrases = pack.intent_phrases if locale == "en" else pack.localization.translations[locale].intent_phrases  # type: ignore[union-attr]
    return ProcedureSummary(
        service_id=pack.service_id,
        title=localized_text(pack, locale, "title", pack.title["en"]),
        short_description=localized_text(pack, locale, "short-description", pack.short_description["en"]),
        intent_phrases=intent_phrases,
        category=pack.category,
        category_label=localized_text(pack, locale, "category-label", pack.category.replace("-", " ")),
        trust_state=loaded.trust_state(now),
        attention_required=fee_attention_required(pack.fee),
    )


def detail_procedure(
    loaded: LoadedProcedure,
    now: datetime | None = None,
    locale: SupportedLocale = "en",
) -> ProcedureDetail:
    pack = loaded.pack
    monitored = [source for source in pack.sources if source.monitoring is not None]
    if not monitored:
        baseline_status = "unavailable"
    elif all(source.monitoring.reviewed_fingerprint is not None for source in monitored):
        baseline_status = "reviewed"
    else:
        baseline_status = "review_required"
    return ProcedureDetail(
        locale=locale,
        translation=translation_info(pack, locale),
        service_id=pack.service_id,
        title=localized_text(pack, locale, "title", pack.title["en"]),
        short_description=localized_text(pack, locale, "short-description", pack.short_description["en"]),
        category=pack.category,
        category_label=localized_text(pack, locale, "category-label", pack.category.replace("-", " ")),
        jurisdiction=pack.jurisdiction,
        department=pack.department,
        official_publisher=pack.publisher,
        interaction_modes=pack.interaction_modes,
        requirements=[item.model_copy(update={"text": localized_text(pack, locale, f"requirement.{item.fact_id}", item.text)}) for item in pack.requirements],
        required_documents=[
            item.model_copy(
                update={
                    "name": localized_text(pack, locale, f"document.{item.document_id}.name", item.name),
                    "guidance": localized_text(pack, locale, f"document.{item.document_id}.guidance", item.guidance),
                }
            )
            for item in pack.required_documents
        ],
        fee=_localized_fee(pack, locale),
        steps=[
            item.model_copy(
                update={
                    "title": localized_text(pack, locale, f"step.{item.step_id}.title", item.title),
                    "instruction": localized_text(pack, locale, f"step.{item.step_id}.instruction", item.instruction),
                }
            )
            for item in pack.steps
        ],
        submission_channels=[
            item.model_copy(
                update={
                    "name": localized_text(pack, locale, f"channel.{item.channel_id}.name", item.name),
                    "guidance": localized_text(pack, locale, f"channel.{item.channel_id}.guidance", item.guidance),
                }
            )
            for item in pack.submission_channels
        ],
        official_handoff_url=pack.official_handoff_url,
        tracking_guidance=pack.tracking_guidance.model_copy(
            update={"text": localized_text(pack, locale, "tracking-guidance", pack.tracking_guidance.text)}
        ) if pack.tracking_guidance else None,
        sources=localized_sources(pack, locale),
        provenance=pack.provenance,
        pack_version=pack.pack_version,
        pack_digest=loaded.digest,
        last_verified_at=pack.last_verified_at,
        review_due_at=pack.review_due_at,
        trust_state=loaded.trust_state(now),
        attention_required=fee_attention_required(pack.fee),
        monitoring=MonitoringTrustInfo(
            prototype_available=bool(monitored),
            continuous_monitoring=False,
            baseline_status=baseline_status,
            human_review_required=True,
            monitored_source_count=len(monitored),
        ),
        limitations=[item.model_copy(update={"text": localized_text(pack, locale, f"limitation.{item.fact_id}", item.text)}) for item in pack.limitations],
        additional_review_items=[
            item.model_copy(update={"text": localized_text(pack, locale, f"additional-review.{item.fact_id}", item.text)})
            for item in pack.readiness.additional_review_items
        ],
    )


def _localized_fee(pack: ProcedurePack, locale: SupportedLocale) -> FeeInformation:
    fee = pack.fee
    claims = [
        claim.model_copy(update={"qualifier": localized_text(pack, locale, f"fee.claim.{index}.qualifier", claim.qualifier)})
        for index, claim in enumerate(fee.claims)
    ]
    return fee.model_copy(
        update={
            "display_message": localized_text(pack, locale, "fee.display-message", fee.display_message),
            "claims": claims,
            "resolution_guidance": localized_text(pack, locale, "fee.resolution-guidance", fee.resolution_guidance)
            if fee.resolution_guidance is not None
            else None,
        }
    )


def localized_sources(pack: ProcedurePack, locale: SupportedLocale, source_ids: set[str] | None = None) -> list[SourceRecord]:
    return [
        source.model_copy(update={"title": localized_text(pack, locale, f"source.{source.source_id}.title", source.title)})
        for source in pack.sources
        if source_ids is None or source.source_id in source_ids
    ]

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, HttpUrl

from sahayi_api.procedures import (
    CitedFact,
    DocumentGuidance,
    FormAssistanceMode,
    FormFieldHandling,
    FormFieldStatus,
    FormAssistanceField,
    Identifier,
    LoadedProcedure,
    PreparationInputType,
    PreparationValidationKind,
    PreparationValueSource,
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
from sahayi_api.readiness import AnswerValue, ReadinessEvaluationResponse, evaluate_readiness


class ChecklistRequest(StrictModel):
    answers: Annotated[dict[Identifier, AnswerValue], Field(default_factory=dict, max_length=30)]


class ChecklistItem(StrictModel):
    item_id: Identifier
    text: str
    source_ids: list[SourceId]


class PersonalizedChecklist(StrictModel):
    locale: SupportedLocale
    translation: TranslationInfo
    service_id: Identifier
    title: ShortText
    pack_version: str
    pack_digest: str
    result: ChecklistItem
    ready: list[ChecklistItem]
    documents: list[DocumentGuidance]
    confirm: list[ChecklistItem]
    steps: list[ChecklistItem]
    warnings: list[ChecklistItem]
    where: list[ChecklistItem]
    sources: list[SourceRecord]
    not_verified: list[ChecklistItem]
    official_handoff_url: HttpUrl
    disclaimer: str


class SyntheticFormRequest(StrictModel):
    persona_id: Identifier | None = None


class SyntheticPersonaResponse(StrictModel):
    persona_id: Identifier
    display_name: ShortText
    synthetic: Literal[True]
    readiness_answers: dict[Identifier, AnswerValue]


class SyntheticFormFieldResponse(StrictModel):
    field_id: Identifier
    label: ShortText
    explanation: str
    value: str | None
    handling: FormFieldHandling
    status: FormFieldStatus
    source_ids: list[SourceId]
    question_id: Identifier | None
    question: str | None
    why_needed: str | None
    input_type: PreparationInputType | None
    required: bool | None
    validation_kind: PreparationValidationKind | None
    minimum_length: int | None
    maximum_length: int | None
    supported_value_sources: list[PreparationValueSource]
    may_appear_on_sheet: bool | None
    confirmation_required: bool | None
    editable: bool | None
    choices: list[dict[str, str]]
    readiness_question_id: Identifier | None
    document_ids: list[Identifier]


class SyntheticFormAssistance(StrictModel):
    locale: SupportedLocale
    translation: TranslationInfo
    service_id: Identifier
    title: ShortText
    mode: FormAssistanceMode
    persona: SyntheticPersonaResponse
    available_personas: list[SyntheticPersonaResponse]
    fields: list[SyntheticFormFieldResponse]
    sources: list[SourceRecord]
    watermark: str
    privacy_notice: str
    disclaimer: str
    official_handoff_url: HttpUrl
    pack_version: str
    pack_digest: str


def localize_preparation_field(
    field: FormAssistanceField,
    locale: SupportedLocale,
    *,
    value: str | None = None,
) -> SyntheticFormFieldResponse:
    return SyntheticFormFieldResponse(
        field_id=field.field_id,
        label=field.label[locale],
        explanation=field.explanation[locale],
        value=value,
        handling=field.handling,
        status=field.status,
        source_ids=field.source_ids,
        question_id=field.question_id,
        question=field.question[locale] if field.question is not None else None,
        why_needed=field.why_needed[locale] if field.why_needed is not None else None,
        input_type=field.input_type,
        required=field.required,
        validation_kind=field.validation.kind if field.validation is not None else None,
        minimum_length=field.validation.minimum_length if field.validation is not None else None,
        maximum_length=field.validation.maximum_length if field.validation is not None else None,
        supported_value_sources=field.supported_value_sources,
        may_appear_on_sheet=field.may_appear_on_sheet,
        confirmation_required=field.confirmation_required,
        editable=field.editable,
        choices=[{"option_id": choice.option_id, "label": choice.label[locale]} for choice in field.choices],
        readiness_question_id=field.readiness_question_id,
        document_ids=field.document_ids,
    )


_COPY = {
    "en": {
        "incomplete": "Complete the readiness questions to personalize this result.",
        "confirm": "Confirm this item with the official service before acting.",
        "not_verified": "Sahayi has not verified approval, processing time, or any fact absent from the cited pack.",
        "checklist_disclaimer": "Preparation guidance only. This is not an eligibility decision, approval, submission, or tracking service.",
        "watermark": "DEMO — NOT FOR SUBMISSION",
        "privacy": "Only fictional demo values are shown. Citizen identifiers and sensitive values must be provided privately to the official service and are not collected by Sahayi.",
        "local_privacy": "Prepared values stay only in this browser memory. They are not sent to Sahayi's server, Groq, logs, or browser storage.",
        "form_disclaimer": "Preparation worksheet only. Sahayi does not fill, submit, download, or track an official form.",
        "local_form_disclaimer": "Sahayi preparation sheet only. Review it locally, then use the verified official channel. Sahayi does not submit or track an official application.",
    },
    "hi": {
        "incomplete": "इस परिणाम को व्यक्तिगत बनाने के लिए तैयारी प्रश्न पूरे करें।",
        "confirm": "कार्रवाई से पहले आधिकारिक सेवा से इस बात की पुष्टि करें।",
        "not_verified": "Sahayi ने स्वीकृति, प्रसंस्करण समय या उद्धृत पैक में न दिए गए किसी तथ्य का सत्यापन नहीं किया है।",
        "checklist_disclaimer": "केवल तैयारी मार्गदर्शन। यह पात्रता निर्णय, स्वीकृति, जमा करने या ट्रैकिंग की सेवा नहीं है।",
        "watermark": "DEMO — NOT FOR SUBMISSION",
        "privacy": "केवल काल्पनिक डेमो मान दिखते हैं। नागरिक पहचान और संवेदनशील मान आधिकारिक सेवा को निजी रूप से देने होंगे; Sahayi उन्हें एकत्र नहीं करता।",
        "local_privacy": "तैयार मान केवल इस ब्राउज़र की मेमोरी में रहते हैं। वे Sahayi सर्वर, Groq, लॉग या ब्राउज़र स्टोरेज को नहीं भेजे जाते।",
        "form_disclaimer": "केवल तैयारी वर्कशीट। Sahayi आधिकारिक फॉर्म भरता, जमा करता, डाउनलोड करता या ट्रैक नहीं करता।",
        "local_form_disclaimer": "केवल Sahayi तैयारी शीट। इसे इसी डिवाइस पर जाँचकर सत्यापित आधिकारिक माध्यम उपयोग करें। Sahayi आवेदन जमा या ट्रैक नहीं करता।",
    },
    "ml": {
        "incomplete": "ഈ ഫലം വ്യക്തിഗതമാക്കാൻ തയ്യാറെടുപ്പ് ചോദ്യങ്ങൾ പൂർത്തിയാക്കുക.",
        "confirm": "നടപടി എടുക്കുന്നതിന് മുമ്പ് ഔദ്യോഗിക സേവനത്തിൽ ഇത് സ്ഥിരീകരിക്കുക.",
        "not_verified": "അംഗീകാരം, പ്രോസസ്സിംഗ് സമയം, അല്ലെങ്കിൽ ഉദ്ധരിച്ച പാക്കിൽ ഇല്ലാത്ത വസ്തുതകൾ Sahayi പരിശോധിച്ചിട്ടില്ല.",
        "checklist_disclaimer": "തയ്യാറെടുപ്പ് മാർഗനിർദേശം മാത്രം. ഇത് അർഹതാ തീരുമാനമോ അംഗീകാരമോ സമർപ്പണമോ ട്രാക്കിംഗ് സേവനമോ അല്ല.",
        "watermark": "DEMO — NOT FOR SUBMISSION",
        "privacy": "സാങ്കൽപ്പിക ഡെമോ മൂല്യങ്ങൾ മാത്രം കാണിക്കുന്നു. പൗരന്റെ തിരിച്ചറിയൽ വിവരങ്ങളും സൂക്ഷ്മ മൂല്യങ്ങളും ഔദ്യോഗിക സേവനത്തിന് സ്വകാര്യമായി നൽകണം; Sahayi അവ ശേഖരിക്കുന്നില്ല.",
        "local_privacy": "തയ്യാറാക്കിയ മൂല്യങ്ങൾ ഈ ബ്രൗസർ മെമ്മറിയിൽ മാത്രം നിലനിൽക്കും. Sahayi സർവർ, Groq, ലോഗുകൾ, ബ്രൗസർ സ്റ്റോറേജ് എന്നിവയിലേക്ക് അയയ്ക്കില്ല.",
        "form_disclaimer": "തയ്യാറെടുപ്പ് വർക്ക്‌ഷീറ്റ് മാത്രം. Sahayi ഔദ്യോഗിക ഫോം പൂരിപ്പിക്കുകയോ സമർപ്പിക്കുകയോ ഡൗൺലോഡ് ചെയ്യുകയോ ട്രാക്ക് ചെയ്യുകയോ ചെയ്യുന്നില്ല.",
        "local_form_disclaimer": "Sahayi തയ്യാറെടുപ്പ് ഷീറ്റ് മാത്രം. ഈ ഉപകരണത്തിൽ പരിശോധിച്ച ശേഷം സ്ഥിരീകരിച്ച ഔദ്യോഗിക ചാനൽ ഉപയോഗിക്കുക. Sahayi അപേക്ഷ സമർപ്പിക്കുകയോ ട്രാക്ക് ചെയ്യുകയോ ഇല്ല.",
    },
}


def build_personalized_checklist(
    loaded: LoadedProcedure,
    answers: dict[str, AnswerValue],
    *,
    locale: SupportedLocale = "en",
) -> PersonalizedChecklist:
    pack = loaded.pack
    readiness = evaluate_readiness(loaded, answers, locale=locale)
    source_ids: set[str] = set()

    def item(item_id: str, text: str, cited: list[str]) -> ChecklistItem:
        source_ids.update(cited)
        return ChecklistItem(item_id=item_id, text=text, source_ids=cited)

    if readiness.outcome is None:
        result = item("readiness-incomplete", _COPY[locale]["incomplete"], readiness.reason_trace[0].source_ids)
    else:
        cited = sorted({source_id for trace in readiness.reason_trace for source_id in trace.source_ids})
        result = item(f"result-{readiness.outcome.outcome_id}", f"{readiness.outcome.title}: {readiness.outcome.explanation}", cited)

    ready = [
        item(f"ready-{requirement.fact_id}", localized_text(pack, locale, f"requirement.{requirement.fact_id}", requirement.text), requirement.source_ids)
        for requirement in pack.requirements
    ]
    documents = [
        document.model_copy(update={
            "name": localized_text(pack, locale, f"document.{document.document_id}.name", document.name),
            "guidance": localized_text(pack, locale, f"document.{document.document_id}.guidance", document.guidance),
        })
        for document in pack.required_documents
    ]
    for document in documents:
        source_ids.update(document.source_ids)

    confirm = [item("confirm-official", _COPY[locale]["confirm"], pack.provenance["official-handoff-url"])]
    if pack.fee.verification_status.value in {"conflicting", "not_stated"}:
        confirm.append(item("confirm-fee", localized_text(pack, locale, "fee.display-message", pack.fee.display_message), pack.fee.source_ids))
    confirm.extend(
        item(
            f"confirm-{review.fact_id}",
            localized_text(pack, locale, f"additional-review.{review.fact_id}", review.text),
            review.source_ids,
        )
        for review in pack.readiness.additional_review_items
    )

    outcome_sources = sorted({source_id for trace in readiness.reason_trace for source_id in trace.source_ids})
    if readiness.complete:
        steps = [item(f"personalized-step-{index + 1}", text, outcome_sources) for index, text in enumerate(readiness.recommended_next_steps)]
    else:
        steps = [
            item(
                f"step-{step.step_id}",
                f"{localized_text(pack, locale, f'step.{step.step_id}.title', step.title)} — {localized_text(pack, locale, f'step.{step.step_id}.instruction', step.instruction)}",
                step.source_ids,
            )
            for step in pack.steps
        ]
    warnings = [
        item(f"warning-{warning.fact_id}", localized_text(pack, locale, f"limitation.{warning.fact_id}", warning.text), warning.source_ids)
        for warning in pack.limitations
    ]
    if readiness.complete and readiness.recommended_next_steps:
        where = [item("where-personalized-path", readiness.recommended_next_steps[-1], outcome_sources)]
    else:
        where = [
            item(
                f"where-{channel.channel_id}",
                f"{localized_text(pack, locale, f'channel.{channel.channel_id}.name', channel.name)} — {localized_text(pack, locale, f'channel.{channel.channel_id}.guidance', channel.guidance)}",
                channel.source_ids,
            )
            for channel in pack.submission_channels
        ]
    not_verified = [item("not-verified", _COPY[locale]["not_verified"], pack.provenance["limitations"])]
    return PersonalizedChecklist(
        locale=locale,
        translation=translation_info(pack, locale),
        service_id=pack.service_id,
        title=localized_text(pack, locale, "title", pack.title["en"]),
        pack_version=pack.pack_version,
        pack_digest=loaded.digest,
        result=result,
        ready=ready,
        documents=documents,
        confirm=confirm,
        steps=steps,
        warnings=warnings,
        where=where,
        sources=localized_sources(pack, locale, source_ids),
        not_verified=not_verified,
        official_handoff_url=readiness.official_handoff_url or pack.official_handoff_url,
        disclaimer=_COPY[locale]["checklist_disclaimer"],
    )


def prepare_synthetic_form_assistance(
    loaded: LoadedProcedure,
    persona_id: str | None = None,
    *,
    locale: SupportedLocale = "en",
    include_demo_values: bool = True,
) -> SyntheticFormAssistance:
    pack = loaded.pack
    definition = pack.assistance
    if definition is None:
        raise ValueError("Form assistance is unavailable")
    personas = {persona.persona_id: persona for persona in definition.personas}
    selected_id = persona_id or definition.personas[0].persona_id
    if selected_id not in personas:
        raise ValueError("Unknown synthetic persona")
    persona = personas[selected_id]
    persona_fields = set(persona.field_ids)
    source_ids = set(definition.form_source_ids)
    fields = []
    for field in definition.preparation_fields:
        source_ids.update(field.source_ids)
        fields.append(localize_preparation_field(
            field,
            locale,
            value=field.demo_value[locale] if include_demo_values and field.demo_value is not None and field.field_id in persona_fields else None,
        ))
    return SyntheticFormAssistance(
        locale=locale,
        translation=translation_info(pack, locale),
        service_id=pack.service_id,
        title=definition.title[locale],
        mode=definition.form_mode,
        persona=SyntheticPersonaResponse(persona_id=persona.persona_id, display_name=persona.display_name[locale], synthetic=True, readiness_answers=persona.readiness_answers),
        available_personas=[
            SyntheticPersonaResponse(
                persona_id=item.persona_id,
                display_name=item.display_name[locale],
                synthetic=True,
                readiness_answers=item.readiness_answers,
            )
            for item in definition.personas
        ],
        fields=fields,
        sources=localized_sources(pack, locale, source_ids),
        watermark=_COPY[locale]["watermark"],
        privacy_notice=_COPY[locale]["privacy" if include_demo_values else "local_privacy"],
        disclaimer=_COPY[locale]["form_disclaimer" if include_demo_values else "local_form_disclaimer"],
        official_handoff_url=pack.official_handoff_url,
        pack_version=pack.pack_version,
        pack_digest=loaded.digest,
    )

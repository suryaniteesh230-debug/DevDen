from __future__ import annotations

from typing import Annotated, Literal, NotRequired, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.errors import GraphRecursionError
from pydantic import Field, HttpUrl, StringConstraints, model_validator

from sahayi_api.agent import AgentRuntime, AssistantTurnRequest, AssistantTurnResponse, run_assistant_turn
from sahayi_api.assistance import PersonalizedChecklist, SyntheticFormAssistance, SyntheticFormFieldResponse, build_personalized_checklist, localize_preparation_field, prepare_synthetic_form_assistance
from sahayi_api.privacy import contains_high_risk_pii
from sahayi_api.procedures import (
    Identifier,
    LoadedProcedure,
    ProcedureSummary,
    PreparationInputType,
    SourceRecord,
    ShortText,
    StrictModel,
    SupportedLocale,
    localized_text,
    summarize_procedure,
)
from sahayi_api.readiness import AnswerValue, ReadinessEvaluationResponse, ReadinessInputError, ReadinessQuestionResponse, evaluate_readiness


MAX_GRAPH_STEPS = 12
MAX_LOCAL_CANDIDATES = 2
MAX_DOCUMENT_EVIDENCE = 8
CloudMessage = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class LocalIntentCandidate(StrictModel):
    service_id: Identifier
    confidence: Annotated[float, Field(ge=0, le=1)]


class AnswerEvent(StrictModel):
    question_id: Identifier
    value: AnswerValue


class ConfirmedDocumentEvidence(StrictModel):
    document_id: Identifier
    appears_relevant: bool
    citizen_confirmed: Literal[True]


class PublicJourneyState(StrictModel):
    service_id: Identifier | None = None
    candidate_service_ids: Annotated[list[Identifier], Field(default_factory=list, max_length=MAX_LOCAL_CANDIDATES)]
    confirmed: bool = False
    answers: Annotated[dict[Identifier, AnswerValue], Field(default_factory=dict, max_length=30)]
    current_question_id: Identifier | None = None
    document_evidence: Annotated[list[ConfirmedDocumentEvidence], Field(default_factory=list, max_length=MAX_DOCUMENT_EVIDENCE)]
    completed_field_ids: Annotated[list[Identifier], Field(default_factory=list, max_length=30)]
    current_preparation_question_id: Identifier | None = None


class ConversationTurnRequest(StrictModel):
    locale: SupportedLocale
    event_type: Literal["start", "confirm_service", "answer", "field_completed", "document_evidence", "cloud_clarification"]
    local_candidates: Annotated[list[LocalIntentCandidate], Field(default_factory=list, max_length=MAX_LOCAL_CANDIDATES)]
    confirmed_service_id: Identifier | None = None
    answer: AnswerEvent | None = None
    document_evidence: ConfirmedDocumentEvidence | None = None
    completed_field_id: Identifier | None = None
    message: CloudMessage | None = None
    consent: bool = False
    state: PublicJourneyState = Field(default_factory=PublicJourneyState)

    @model_validator(mode="after")
    def validate_event_shape(self) -> "ConversationTurnRequest":
        if self.event_type == "cloud_clarification":
            if self.message is None or self.consent is not True or self.local_candidates:
                raise ValueError("Invalid cloud clarification")
        elif self.message is not None or self.consent:
            raise ValueError("Message and consent are restricted to cloud clarification")
        if self.event_type == "start" and self.confirmed_service_id is not None:
            raise ValueError("Start cannot confirm a service")
        if self.event_type == "confirm_service" and self.confirmed_service_id is None:
            raise ValueError("Confirmation requires a service")
        if self.event_type == "answer" and self.answer is None:
            raise ValueError("Answer event requires an answer")
        if self.event_type == "document_evidence" and self.document_evidence is None:
            raise ValueError("Document event requires evidence")
        if self.event_type == "field_completed" and self.completed_field_id is None:
            raise ValueError("Field completion requires a field ID")
        if self.event_type != "answer" and self.answer is not None:
            raise ValueError("Unexpected answer")
        if self.event_type != "document_evidence" and self.document_evidence is not None:
            raise ValueError("Unexpected document evidence")
        if self.event_type != "field_completed" and self.completed_field_id is not None:
            raise ValueError("Unexpected completed field")
        return self


class SafeUiAction(StrictModel):
    action_id: Literal["confirm_service", "choose_service", "answer", "attach_document", "open_official_service", "browse_services"]
    label: ShortText
    service_id: Identifier | None = None
    question_id: Identifier | None = None
    value: AnswerValue | None = None


class ConversationTurnResponse(StrictModel):
    status: Literal["ok", "blocked", "unsupported", "unavailable", "error"]
    locale: SupportedLocale
    assistant_message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1600)]
    next_action: Literal["confirm_service", "choose_service", "ask_user", "prepared", "official_handoff", "unsupported", "blocked", "error"]
    progress_text: ShortText | None
    actions: Annotated[list[SafeUiAction], Field(max_length=12)]
    active_procedure: ProcedureSummary | None
    current_question: ReadinessQuestionResponse | None
    current_preparation_question: SyntheticFormFieldResponse | None
    readiness: ReadinessEvaluationResponse | None
    checklist: PersonalizedChecklist | None
    preparation: SyntheticFormAssistance | None
    prepared_field_count: int
    preparation_field_count: int
    missing_required_field_ids: list[Identifier]
    document_helper_available: bool
    accepted_document_evidence: Annotated[list[ConfirmedDocumentEvidence], Field(max_length=MAX_DOCUMENT_EVIDENCE)]
    contextual_sources: Annotated[list[SourceRecord], Field(max_length=20)]
    official_handoff_url: HttpUrl | None
    state: PublicJourneyState
    diagnostic_category: Literal["none", "pii_blocked", "invalid_state", "provider_unavailable", "provider_failure", "budget_exhausted"]


class GraphState(TypedDict):
    request: ConversationTurnRequest
    public_state: PublicJourneyState
    status: Literal["ok", "blocked", "unsupported", "unavailable", "error"]
    next_action: str
    assistant_message: str
    progress_text: str | None
    actions: list[SafeUiAction]
    active_procedure: ProcedureSummary | None
    readiness: ReadinessEvaluationResponse | None
    current_preparation_question: SyntheticFormFieldResponse | None
    checklist: PersonalizedChecklist | None
    preparation: SyntheticFormAssistance | None
    prepared_field_count: int
    preparation_field_count: int
    missing_required_field_ids: list[Identifier]
    document_helper_available: bool
    contextual_sources: list[SourceRecord]
    official_handoff_url: HttpUrl | None
    diagnostic_category: str
    llm_calls: int
    agent_response: NotRequired[AssistantTurnResponse | None]


_COPY = {
    "en": {
        "unsupported": "Sahayi does not have a verified procedure for that request. You can browse the two supported services.",
        "blocked": "I cannot use that message because it may contain identifying information. Remove identifiers, contact details, addresses, and document text, then try again.",
        "confirm": "I found a verified service that may match. Is this what you need?",
        "choose": "Please choose the supported service you mean.",
        "checking": "Checking the verified procedure…",
        "reviewing": "Reviewing what you still need…",
        "preparing": "Preparing your next step…",
        "prepared": "Your preparation guidance is ready. Review anything still missing before using the verified official channel.",
        "error": "I could not safely continue this turn. Start over or browse the supported services.",
        "confirm_action": "Yes, continue",
        "browse": "Browse supported services",
        "document": "Check a document on this device",
        "official": "Open the official service",
    },
    "hi": {
        "unsupported": "इस अनुरोध के लिए Sahayi के पास सत्यापित प्रक्रिया नहीं है। आप दो समर्थित सेवाएँ देख सकते हैं।",
        "blocked": "इस संदेश में पहचान संबंधी जानकारी हो सकती है, इसलिए मैं इसका उपयोग नहीं कर सकता। पहचान, संपर्क, पता और दस्तावेज़ का पाठ हटाकर फिर प्रयास करें।",
        "confirm": "मुझे एक सत्यापित सेवा मिली है जो मेल खा सकती है। क्या आपको यही चाहिए?",
        "choose": "कृपया वह समर्थित सेवा चुनें जिसका आप मतलब रखते हैं।",
        "checking": "सत्यापित प्रक्रिया जाँची जा रही है…",
        "reviewing": "जो अभी चाहिए उसकी समीक्षा की जा रही है…",
        "preparing": "आपका अगला कदम तैयार किया जा रहा है…",
        "prepared": "आपका तैयारी मार्गदर्शन तैयार है। सत्यापित आधिकारिक माध्यम का उपयोग करने से पहले बाकी चीज़ें जाँच लें।",
        "error": "मैं इस चरण को सुरक्षित रूप से जारी नहीं रख सका। फिर से शुरू करें या समर्थित सेवाएँ देखें।",
        "confirm_action": "हाँ, आगे बढ़ें",
        "browse": "समर्थित सेवाएँ देखें",
        "document": "इस डिवाइस पर दस्तावेज़ जाँचें",
        "official": "आधिकारिक सेवा खोलें",
    },
    "ml": {
        "unsupported": "ഈ അഭ്യർത്ഥനയ്ക്ക് Sahayiയിൽ പരിശോധിച്ച നടപടിയില്ല. പിന്തുണയുള്ള രണ്ട് സേവനങ്ങൾ കാണാം.",
        "blocked": "ഈ സന്ദേശത്തിൽ തിരിച്ചറിയൽ വിവരങ്ങൾ ഉണ്ടായേക്കാം, അതിനാൽ ഇത് ഉപയോഗിക്കാനാവില്ല. തിരിച്ചറിയൽ, ബന്ധപ്പെടൽ, വിലാസം, രേഖയിലെ വാചകം എന്നിവ നീക്കി വീണ്ടും ശ്രമിക്കുക.",
        "confirm": "പൊരുത്തപ്പെടാവുന്ന ഒരു പരിശോധിച്ച സേവനം കണ്ടെത്തി. ഇതാണോ വേണ്ടത്?",
        "choose": "നിങ്ങൾ ഉദ്ദേശിക്കുന്ന പിന്തുണയുള്ള സേവനം തിരഞ്ഞെടുക്കുക.",
        "checking": "പരിശോധിച്ച നടപടി പരിശോധിക്കുന്നു…",
        "reviewing": "ഇനിയും വേണ്ടത് പരിശോധിക്കുന്നു…",
        "preparing": "അടുത്ത ഘട്ടം തയ്യാറാക്കുന്നു…",
        "prepared": "തയ്യാറെടുപ്പ് മാർഗനിർദേശം തയ്യാറായി. പരിശോധിച്ച ഔദ്യോഗിക ചാനൽ ഉപയോഗിക്കുന്നതിന് മുമ്പ് ബാക്കിയുള്ളവ പരിശോധിക്കുക.",
        "error": "ഈ ഘട്ടം സുരക്ഷിതമായി തുടരാനായില്ല. വീണ്ടും തുടങ്ങുക അല്ലെങ്കിൽ പിന്തുണയുള്ള സേവനങ്ങൾ കാണുക.",
        "confirm_action": "അതെ, തുടരുക",
        "browse": "പിന്തുണയുള്ള സേവനങ്ങൾ കാണുക",
        "document": "ഈ ഉപകരണത്തിൽ രേഖ പരിശോധിക്കുക",
        "official": "ഔദ്യോഗിക സേവനം തുറക്കുക",
    },
}


def _base_state(turn: ConversationTurnRequest) -> GraphState:
    return {
        "request": turn,
        "public_state": turn.state.model_copy(deep=True),
        "status": "ok",
        "next_action": "error",
        "assistant_message": _COPY[turn.locale]["error"],
        "progress_text": None,
        "actions": [],
        "active_procedure": None,
        "readiness": None,
        "current_preparation_question": None,
        "checklist": None,
        "preparation": None,
        "prepared_field_count": 0,
        "preparation_field_count": 0,
        "missing_required_field_ids": [],
        "document_helper_available": False,
        "contextual_sources": [],
        "official_handoff_url": None,
        "diagnostic_category": "none",
        "llm_calls": 0,
    }


def build_conversation_graph(
    registry: dict[str, LoadedProcedure],
    runtime: AgentRuntime,
    client_address: str,
):
    def safety(state: GraphState) -> dict:
        turn = state["request"]
        if turn.message is not None and contains_high_risk_pii(turn.message):
            return {
                "status": "blocked",
                "next_action": "blocked",
                "assistant_message": _COPY[turn.locale]["blocked"],
                "diagnostic_category": "pii_blocked",
            }
        return {}

    def intent(state: GraphState) -> dict:
        turn = state["request"]
        public = state["public_state"].model_copy(deep=True)
        if public.service_id is not None and public.service_id not in registry:
            return _invalid_state(turn.locale)
        if any(service_id not in registry for service_id in public.candidate_service_ids):
            return _invalid_state(turn.locale)

        if turn.event_type == "cloud_clarification":
            response = state.get("agent_response")
            if response is None:
                return _invalid_state(turn.locale)
            choices = response.selection.choices
            candidate_ids = [choice.service_id for choice in choices if choice.service_id in registry]
            if response.selection.service_id in registry:
                candidate_ids = [response.selection.service_id]
            candidate_ids = list(dict.fromkeys(candidate_ids))[:MAX_LOCAL_CANDIDATES]
            if not candidate_ids:
                diagnostic = "provider_unavailable" if response.status == "unavailable" else "provider_failure"
                return _unsupported(turn.locale, diagnostic=diagnostic, agent_response=response)
            public = PublicJourneyState(candidate_service_ids=candidate_ids)
            return _proposal(turn.locale, public, registry, response.message, agent_response=response, llm_calls=1)

        if turn.event_type == "start":
            candidate_ids = list(dict.fromkeys(candidate.service_id for candidate in turn.local_candidates))
            if any(service_id not in registry for service_id in candidate_ids):
                return _invalid_state(turn.locale)
            if not candidate_ids:
                return _unsupported(turn.locale)
            public = PublicJourneyState(candidate_service_ids=candidate_ids)
            return _proposal(turn.locale, public, registry)

        if turn.event_type == "confirm_service":
            service_id = turn.confirmed_service_id
            if service_id not in registry or service_id not in public.candidate_service_ids:
                return _invalid_state(turn.locale)
            public = PublicJourneyState(service_id=service_id, candidate_service_ids=[], confirmed=True)
            return {"public_state": public, "progress_text": _COPY[turn.locale]["checking"]}

        if not public.confirmed or public.service_id not in registry:
            return _invalid_state(turn.locale)
        return {"public_state": public}

    def procedure_router(state: GraphState) -> dict:
        turn = state["request"]
        service_id = state["public_state"].service_id
        if service_id not in registry:
            return _invalid_state(turn.locale)
        return {
            "active_procedure": summarize_procedure(registry[service_id], locale=turn.locale),
            "progress_text": _COPY[turn.locale]["reviewing"],
        }

    def document_evidence(state: GraphState) -> dict:
        turn = state["request"]
        public = state["public_state"].model_copy(deep=True)
        loaded = registry[public.service_id or ""]
        allowed = {item.document_id for item in loaded.pack.required_documents}
        existing: dict[str, ConfirmedDocumentEvidence] = {}
        for item in public.document_evidence:
            if item.document_id not in allowed:
                return _invalid_state(turn.locale)
            existing[item.document_id] = item
        if turn.document_evidence is not None:
            if turn.document_evidence.document_id not in allowed:
                return _invalid_state(turn.locale)
            existing[turn.document_evidence.document_id] = turn.document_evidence
        public.document_evidence = list(existing.values())[:MAX_DOCUMENT_EVIDENCE]
        return {"public_state": public}

    def interview(state: GraphState) -> dict:
        turn = state["request"]
        public = state["public_state"].model_copy(deep=True)
        loaded = registry[public.service_id or ""]
        definition = loaded.pack.assistance
        if definition is None:
            return _invalid_state(turn.locale)
        fields = definition.preparation_fields
        collectable = {
            field.field_id: field
            for field in fields
            if field.input_type in {PreparationInputType.TEXT, PreparationInputType.TEXTAREA, PreparationInputType.SINGLE_CHOICE, PreparationInputType.DOCUMENT_CLUE}
        }
        if len(public.completed_field_ids) != len(set(public.completed_field_ids)) or not set(public.completed_field_ids) <= collectable.keys():
            return _invalid_state(turn.locale)
        try:
            before = evaluate_readiness(loaded, public.answers, locale=turn.locale)
            if public.current_question_id is not None:
                if before.next_question is None or public.current_question_id != before.next_question.question_id:
                    return _invalid_state(turn.locale)
            if turn.answer is not None:
                if before.next_question is None or turn.answer.question_id != before.next_question.question_id:
                    return _invalid_state(turn.locale)
                public.answers[turn.answer.question_id] = turn.answer.value
            result = evaluate_readiness(loaded, public.answers, locale=turn.locale)
        except ReadinessInputError:
            return _invalid_state(turn.locale)

        public.current_question_id = result.next_question.question_id if result.next_question else None
        if result.next_question is not None:
            actions = _question_actions(result)
            helper = _question_uses_document(result.next_question.question_id)
            if helper:
                actions.append(SafeUiAction(action_id="attach_document", label=_COPY[turn.locale]["document"]))
            return {
                "public_state": public,
                "readiness": result,
                "assistant_message": result.next_question.prompt,
                "next_action": "ask_user",
                "actions": actions,
                "document_helper_available": helper,
                "contextual_sources": result.sources,
            }

        derived_ids = {
            field.field_id
            for field in fields
            if field.input_type is PreparationInputType.READINESS_VALUE and field.readiness_question_id in public.answers
        }
        completed_ids = set(public.completed_field_ids) | derived_ids
        if turn.completed_field_id is not None:
            previous = next((field for field in fields if field.question_id == public.current_preparation_question_id), None)
            if previous is None or previous.field_id != turn.completed_field_id or turn.completed_field_id not in collectable:
                return _invalid_state(turn.locale)
            completed_ids.add(turn.completed_field_id)
            public.completed_field_ids = sorted(completed_ids & collectable.keys())

        applicable_fields = [
            field
            for field in fields
            if field.input_type is not PreparationInputType.NOT_COLLECTED
            and (
                field.input_type is not PreparationInputType.READINESS_VALUE
                or field.readiness_question_id in public.answers
            )
        ]
        required_fields = [field for field in applicable_fields if field.required is True]
        missing = [field for field in required_fields if field.field_id not in completed_ids]
        next_field = next((field for field in missing if field.field_id in collectable), None)
        public.current_preparation_question_id = next_field.question_id if next_field is not None else None
        prepared_count = len([field for field in applicable_fields if field.field_id in completed_ids])
        preparation_count = len(applicable_fields)
        if next_field is not None:
            question = localize_preparation_field(next_field, turn.locale)
            return {
                "public_state": public,
                "readiness": result,
                "current_preparation_question": question,
                "assistant_message": question.question or question.label,
                "next_action": "ask_user",
                "actions": [],
                "document_helper_available": next_field.input_type is PreparationInputType.DOCUMENT_CLUE,
                "contextual_sources": result.sources,
                "prepared_field_count": prepared_count,
                "preparation_field_count": preparation_count,
                "missing_required_field_ids": [field.field_id for field in missing],
            }
        return {
            "public_state": public,
            "readiness": result,
            "assistant_message": result.outcome.explanation if result.outcome else _COPY[turn.locale]["prepared"],
            "next_action": "prepared",
            "actions": [],
            "progress_text": _COPY[turn.locale]["preparing"],
            "contextual_sources": result.sources,
            "prepared_field_count": prepared_count,
            "preparation_field_count": preparation_count,
            "missing_required_field_ids": [],
        }

    def checklist(state: GraphState) -> dict:
        public = state["public_state"]
        turn = state["request"]
        loaded = registry[public.service_id or ""]
        return {"checklist": build_personalized_checklist(loaded, public.answers, locale=turn.locale)}

    def preparation(state: GraphState) -> dict:
        public = state["public_state"]
        turn = state["request"]
        loaded = registry[public.service_id or ""]
        return {"preparation": prepare_synthetic_form_assistance(loaded, locale=turn.locale, include_demo_values=False)}

    def explanation(state: GraphState) -> dict:
        if state["current_preparation_question"] is not None:
            return {}
        if state["readiness"] is not None and state["readiness"].complete:
            return {"assistant_message": _COPY[state["request"].locale]["prepared"]}
        return {}

    def official_handoff(state: GraphState) -> dict:
        public = state["public_state"]
        turn = state["request"]
        loaded = registry[public.service_id or ""]
        url = loaded.pack.official_handoff_url
        return {
            "next_action": "official_handoff",
            "official_handoff_url": url,
            "actions": [SafeUiAction(action_id="open_official_service", label=_COPY[turn.locale]["official"])],
            "progress_text": None,
        }

    builder = StateGraph(GraphState)
    builder.add_node("safety_consent", safety)
    builder.add_node("intent_clarification", intent)
    builder.add_node("procedure_router", procedure_router)
    builder.add_node("document_evidence", document_evidence)
    builder.add_node("interview_readiness", interview)
    builder.add_node("checklist", checklist)
    builder.add_node("preparation", preparation)
    builder.add_node("explanation", explanation)
    builder.add_node("official_handoff", official_handoff)
    builder.add_edge(START, "safety_consent")
    builder.add_conditional_edges("safety_consent", lambda state: END if state["status"] != "ok" else "intent_clarification")
    builder.add_conditional_edges("intent_clarification", _after_intent)
    builder.add_edge("procedure_router", "document_evidence")
    builder.add_edge("document_evidence", "interview_readiness")
    builder.add_conditional_edges("interview_readiness", _after_interview)
    builder.add_edge(["checklist", "preparation"], "explanation")
    builder.add_conditional_edges("explanation", lambda state: "official_handoff" if state["readiness"] and state["readiness"].complete and state["current_preparation_question"] is None else END)
    builder.add_edge("official_handoff", END)
    return builder.compile()


async def run_conversation_turn(
    turn: ConversationTurnRequest,
    registry: dict[str, LoadedProcedure],
    runtime: AgentRuntime,
    client_address: str,
) -> ConversationTurnResponse:
    graph = build_conversation_graph(registry, runtime, client_address)
    initial = _base_state(turn)
    if turn.event_type == "cloud_clarification":
        initial["agent_response"] = await run_assistant_turn(
            AssistantTurnRequest(
                locale=turn.locale,
                message=turn.message or "",
                history=[],
                service_id=turn.state.service_id,
                readiness_answers=turn.state.answers,
                demo_status_id=None,
                consent=True,
            ),
            registry,
            runtime,
            client_address,
            graph_node="safety_intent",
        )
        initial["llm_calls"] = 1
    try:
        state = graph.invoke(initial, config={"recursion_limit": MAX_GRAPH_STEPS})
    except GraphRecursionError:
        state = {**_base_state(turn), **_budget_exhausted(turn.locale)}
    except Exception:
        state = {**_base_state(turn), **_invalid_state(turn.locale)}
    public = state["public_state"]
    readiness = state.get("readiness")
    return ConversationTurnResponse(
        status=state["status"],
        locale=turn.locale,
        assistant_message=state["assistant_message"],
        next_action=state["next_action"],
        progress_text=state["progress_text"],
        actions=state["actions"],
        active_procedure=state["active_procedure"],
        current_question=readiness.next_question if readiness else None,
        current_preparation_question=state["current_preparation_question"],
        readiness=readiness,
        checklist=state["checklist"],
        preparation=state["preparation"],
        prepared_field_count=state["prepared_field_count"],
        preparation_field_count=state["preparation_field_count"],
        missing_required_field_ids=state["missing_required_field_ids"],
        document_helper_available=state["document_helper_available"],
        accepted_document_evidence=public.document_evidence,
        contextual_sources=state["contextual_sources"],
        official_handoff_url=state["official_handoff_url"],
        state=public,
        diagnostic_category=state["diagnostic_category"],
    )


def _proposal(
    locale: SupportedLocale,
    public: PublicJourneyState,
    registry: dict[str, LoadedProcedure],
    message: str | None = None,
    *,
    agent_response: AssistantTurnResponse | None = None,
    llm_calls: int = 0,
) -> dict:
    choices = [summarize_procedure(registry[service_id], locale=locale) for service_id in public.candidate_service_ids]
    single = len(choices) == 1
    actions = [
        SafeUiAction(
            action_id="confirm_service" if single else "choose_service",
            label=_COPY[locale]["confirm_action"] if single else item.title,
            service_id=item.service_id,
        )
        for item in choices
    ]
    return {
        "public_state": public,
        "assistant_message": message or (_COPY[locale]["confirm"] if single else _COPY[locale]["choose"]),
        "next_action": "confirm_service" if single else "choose_service",
        "actions": actions,
        "agent_response": agent_response,
        "llm_calls": llm_calls,
    }


def _unsupported(locale: SupportedLocale, *, diagnostic: str = "none", agent_response: AssistantTurnResponse | None = None) -> dict:
    return {
        "status": "unsupported" if diagnostic == "none" else "unavailable",
        "next_action": "unsupported",
        "assistant_message": _COPY[locale]["unsupported"],
        "actions": [SafeUiAction(action_id="browse_services", label=_COPY[locale]["browse"])],
        "diagnostic_category": diagnostic,
        "agent_response": agent_response,
        "llm_calls": 1 if agent_response is not None else 0,
    }


def _invalid_state(locale: SupportedLocale) -> dict:
    return {
        "status": "error",
        "next_action": "error",
        "assistant_message": _COPY[locale]["error"],
        "actions": [SafeUiAction(action_id="browse_services", label=_COPY[locale]["browse"])],
        "diagnostic_category": "invalid_state",
    }


def _budget_exhausted(locale: SupportedLocale) -> dict:
    return {
        "status": "error",
        "next_action": "error",
        "assistant_message": _COPY[locale]["error"],
        "actions": [SafeUiAction(action_id="browse_services", label=_COPY[locale]["browse"])],
        "diagnostic_category": "budget_exhausted",
    }


def _after_intent(state: GraphState):
    if state["status"] != "ok" or not state["public_state"].confirmed:
        return END
    return "procedure_router"


def _after_interview(state: GraphState):
    if state["status"] != "ok":
        return END
    if state["readiness"] is not None:
        return ["checklist", "preparation"]
    return END


def _question_actions(readiness: ReadinessEvaluationResponse) -> list[SafeUiAction]:
    question = readiness.next_question
    if question is None:
        return []
    if question.answer_type.value == "boolean":
        labels = {"en": ("Yes", "No"), "hi": ("हाँ", "नहीं"), "ml": ("അതെ", "അല്ല")}[readiness.locale]
        return [
            SafeUiAction(action_id="answer", label=label, question_id=question.question_id, value=value)
            for label, value in zip(labels, (True, False), strict=True)
        ]
    if question.options:
        return [
            SafeUiAction(action_id="answer", label=option.label, question_id=question.question_id, value=option.option_id)
            for option in question.options
        ]
    return []


def _question_uses_document(question_id: str) -> bool:
    return any(token in question_id for token in ("document", "proof", "certificate", "record", "poa"))

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import secrets
import time
import unicodedata
from collections import defaultdict, deque
from copy import deepcopy
from typing import Annotated, Any, Literal, Protocol

from pydantic import Field, StringConstraints, ValidationError

from sahayi_api.assistance import build_personalized_checklist, prepare_synthetic_form_assistance
from sahayi_api.config import AGENT_PROVIDER, GROQ_BASE_URL, Settings
from sahayi_api.privacy import conversation_contains_high_risk_pii
from sahayi_api.procedures import (
    Identifier,
    LoadedProcedure,
    ShortText,
    SourceRecord,
    StrictModel,
    SupportedLocale,
    detail_procedure,
    localized_sources,
    localized_text,
    summarize_procedure,
)
from sahayi_api.readiness import AnswerValue, ReadinessInputError, evaluate_readiness
from sahayi_api.simulation import DemoStatusId, explain_simulated_status


logger = logging.getLogger(__name__)

CurrentMessage = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
PriorContent = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]

TOOL_NAMES = (
    "list_supported_services",
    "get_verified_procedure",
    "get_readiness_questions",
    "evaluate_readiness",
    "build_personalized_checklist",
    "prepare_synthetic_form_assistance",
    "explain_simulated_status",
)
AgentGraphNode = Literal[
    "safety_intent",
    "procedure_routing",
    "readiness_interview",
    "automatic_preparation",
    "explanation_status",
    "official_handoff",
]
NODE_TOOL_NAMES: dict[AgentGraphNode, tuple[str, ...]] = {
    "safety_intent": ("list_supported_services",),
    "procedure_routing": ("list_supported_services", "get_verified_procedure"),
    "readiness_interview": ("get_readiness_questions", "evaluate_readiness"),
    "automatic_preparation": ("build_personalized_checklist", "prepare_synthetic_form_assistance"),
    "explanation_status": ("explain_simulated_status",),
    "official_handoff": (),
}
ACTION_IDS = {
    "view-procedure",
    "start-readiness",
    "build-checklist",
    "prepare-synthetic-form",
    "open-official-service",
}
_UNSAFE_MODEL_PROSE = re.compile(
    r"(?iu)https?://|www\.|\b(?:you are|application is) (?:approved|eligible)\b|"
    r"\b(?:the )?fee is\s*(?:₹|rs\.?|inr)|\bI (?:submitted|filled|tracked|monitored)\b|"
    r"आप (?:पात्र|स्वीकृत) हैं|आवेदन स्वीकृत है|शुल्क (?:₹|रु|rs)|"
    r"നിങ്ങൾ (?:അർഹനാണ്|അർഹയാണ്)|അപേക്ഷ അംഗീകരിച്ചു|ഫീസ് (?:₹|rs)"
)
_SAFE_PROVIDER_ERROR_TYPES = {
    "api_error",
    "authentication_error",
    "invalid_request_error",
    "permission_error",
    "rate_limit_error",
    "server_error",
}
_SAFE_PROVIDER_ERROR_CODES = {
    "authentication_error",
    "invalid_request_error",
    "json_schema_invalid",
    "permission_denied",
    "rate_limit_exceeded",
    "server_error",
}
_SAFE_PROVIDER_ERROR_PARAM = re.compile(
    r"^(?:max_completion_tokens|messages|model|parallel_tool_calls|stream|tool_choice|tools)"
    r"(?:\[[0-9]{1,3}\]|\.[A-Za-z_][A-Za-z0-9_]{0,63})*$"
)
_SAFE_EXCEPTION_TYPES = {
    "APIConnectionError",
    "APIError",
    "APIStatusError",
    "APITimeoutError",
    "AuthenticationError",
    "BadRequestError",
    "InternalServerError",
    "PermissionDeniedError",
    "RateLimitError",
    "RuntimeError",
    "TimeoutError",
    "ValidationError",
}
_JSON_SCHEMA_TYPES = {"array", "boolean", "integer", "null", "number", "object", "string"}
_TOOL_CALL_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class PriorMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: PriorContent


class AssistantTurnRequest(StrictModel):
    locale: SupportedLocale
    message: CurrentMessage
    history: Annotated[list[PriorMessage], Field(default_factory=list, max_length=4)]
    service_id: Identifier | None = None
    readiness_answers: Annotated[dict[Identifier, AnswerValue], Field(default_factory=dict, max_length=30)]
    synthetic_persona_id: Identifier | None = None
    demo_status_id: DemoStatusId | None = None
    consent: Literal[True]


class ServiceChoice(StrictModel):
    service_id: Identifier
    title: ShortText


class SelectionState(StrictModel):
    state: Literal["none", "clarification", "selected"]
    service_id: Identifier | None
    choices: Annotated[list[ServiceChoice], Field(max_length=4)]


class FactCard(StrictModel):
    card_id: Identifier
    title: ShortText
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2400)]
    source_ids: Annotated[list[str], Field(max_length=12)]


class AgentAction(StrictModel):
    action_id: Identifier
    label: ShortText
    service_id: Identifier | None


class AssistantTurnResponse(StrictModel):
    status: Literal["ok", "fallback", "blocked", "unavailable", "rate_limited"]
    locale: SupportedLocale
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1600)]
    selection: SelectionState
    fact_cards: Annotated[list[FactCard], Field(max_length=8)]
    sources: Annotated[list[SourceRecord], Field(max_length=20)]
    actions: Annotated[list[AgentAction], Field(max_length=8)]
    tool_trace: Annotated[list[Literal[
        "list_supported_services",
        "get_verified_procedure",
        "get_readiness_questions",
        "evaluate_readiness",
        "build_personalized_checklist",
        "prepare_synthetic_form_assistance",
        "explain_simulated_status",
    ]], Field(max_length=8)]
    disclaimer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=800)]
    fallback: bool


class AgentModelOutput(StrictModel):
    guidance_message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1200)]
    selection_state: Literal["none", "clarification", "selected"]
    service_id: str | None
    action_ids: Annotated[list[Literal[
        "view-procedure",
        "start-readiness",
        "build-checklist",
        "prepare-synthetic-form",
        "open-official-service",
    ]], Field(max_length=8)]


class ToolServiceListInput(StrictModel):
    locale: SupportedLocale


class ToolProcedureInput(StrictModel):
    service_id: Identifier
    locale: SupportedLocale


class ToolReadinessAnswer(StrictModel):
    question_id: Identifier
    value: AnswerValue


class ToolReadinessInput(ToolProcedureInput):
    answers: Annotated[list[ToolReadinessAnswer], Field(max_length=30)]


class ToolPersonaInput(ToolProcedureInput):
    persona_id: Identifier | None


class ToolStatusInput(ToolProcedureInput):
    status_id: DemoStatusId


class ChatCompletionsClient(Protocol):
    chat: Any


class AgentProvider(Protocol):
    @property
    def available(self) -> bool: ...

    def get_client(self) -> ChatCompletionsClient: ...


class GroqProvider:
    """Application-controlled Groq Chat Completions configuration."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client: ChatCompletionsClient | None = None

    @property
    def available(self) -> bool:
        return (
            self.settings.agent_enabled
            and self.settings.agent_configuration_valid
            and self.settings.agent_provider == AGENT_PROVIDER
            and bool(self.settings.groq_api_key)
        )

    def get_client(self) -> ChatCompletionsClient:
        if self.client is None:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI(
                api_key=self.settings.groq_api_key,
                base_url=GROQ_BASE_URL,
                timeout=self.settings.agent_timeout_seconds,
                max_retries=0,
            )
        return self.client


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._salt = secrets.token_bytes(32)
        self._entries: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    def client_key(self, address: str) -> str:
        return hashlib.blake2b(address.encode("utf-8"), key=self._salt, digest_size=16).hexdigest()

    async def allow(self, key: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        cutoff = current - self.window_seconds
        async with self._lock:
            for entry_key in list(self._entries):
                queue = self._entries[entry_key]
                while queue and queue[0] <= cutoff:
                    queue.popleft()
                if not queue:
                    del self._entries[entry_key]
            queue = self._entries[key]
            if len(queue) >= self.limit:
                return False
            queue.append(current)
            return True


class RequestBudget:
    def __init__(self, limit: int) -> None:
        self.remaining = limit
        self._lock = asyncio.Lock()

    async def take(self) -> bool:
        async with self._lock:
            if self.remaining <= 0:
                return False
            self.remaining -= 1
            return True


class AgentRuntime:
    def __init__(self, settings: Settings, provider: AgentProvider | None = None) -> None:
        self.settings = settings
        self.provider = provider or GroqProvider(settings)
        self.rate_limiter = RateLimiter(settings.agent_rate_limit, settings.agent_rate_window_seconds)
        self.request_budget = RequestBudget(settings.agent_request_budget)
        self.semaphore = asyncio.Semaphore(settings.agent_concurrency)
        self.client: ChatCompletionsClient | None = None

    @property
    def available(self) -> bool:
        return self.provider.available

    def get_client(self) -> ChatCompletionsClient:
        if self.client is None:
            self.client = self.provider.get_client()
        return self.client


_COPY = {
    "en": {
        "blocked": "I cannot use that message because it may contain personal identifying information. Remove identifiers, contact details, addresses, and document data, then try again.",
        "unavailable": "Ask Sahayi AI is unavailable. You can still browse verified procedures and use the deterministic readiness check.",
        "fallback": "I could not complete the AI-guided turn. The verified procedure catalogue and deterministic checks remain available.",
        "rate": "Ask Sahayi AI is receiving too many requests. Please use the deterministic guidance or try again later.",
        "disclaimer": "AI guidance is a prototype, may be wrong, and is never an eligibility decision or approval. Official sources prevail.",
        "clarify": "Choose one supported service so I can use only its verified guidance.",
        "view": "View verified procedure",
        "readiness": "Start deterministic readiness check",
        "checklist": "Build personalized checklist",
        "form": "Prepare synthetic demo worksheet",
        "official": "Open official service",
        "requirements": "Verified requirements",
        "fee": "Fee information",
        "switch": "This request appears to match a different verified Sahayi service. Choose it to switch without using facts from the currently selected service.",
        "address_clarify": "Do you mean an Aadhaar address update, or help related to the address on your Kerala pension record? Sahayi has a verified Aadhaar address-update procedure, but no separate verified pension-record address-change procedure, so I will not assume either. Choose the relevant verified service.",
        "pension_address_scope": "Sahayi's verified catalogue does not contain a separate pension-record address-change procedure. You can keep the Kerala pension service selected for its verified general guidance, but Sahayi will not invent address-change steps.",
        "invite": "Tell me which government service you need help with, such as an Aadhaar address update or Kerala old-age pension.",
    },
    "hi": {
        "blocked": "मैं इस संदेश का उपयोग नहीं कर सकता क्योंकि इसमें निजी पहचान जानकारी हो सकती है। पहचान, संपर्क, पता और दस्तावेज़ विवरण हटाकर फिर प्रयास करें।",
        "unavailable": "Ask Sahayi AI उपलब्ध नहीं है। आप सत्यापित प्रक्रियाएँ और नियत तैयारी जाँच अभी भी उपयोग कर सकते हैं।",
        "fallback": "AI-मार्गदर्शित चरण पूरा नहीं हो सका। सत्यापित प्रक्रिया सूची और नियत जाँच उपलब्ध हैं।",
        "rate": "Ask Sahayi AI पर अभी बहुत अधिक अनुरोध हैं। नियत मार्गदर्शन उपयोग करें या बाद में प्रयास करें।",
        "disclaimer": "AI मार्गदर्शन एक प्रोटोटाइप है, गलत हो सकता है और कभी भी पात्रता निर्णय या स्वीकृति नहीं है। आधिकारिक स्रोत मान्य हैं।",
        "clarify": "केवल सत्यापित मार्गदर्शन उपयोग करने के लिए एक समर्थित सेवा चुनें।",
        "view": "सत्यापित प्रक्रिया देखें",
        "readiness": "नियत तैयारी जाँच शुरू करें",
        "checklist": "व्यक्तिगत चेकलिस्ट बनाएँ",
        "form": "कृत्रिम डेमो वर्कशीट तैयार करें",
        "official": "आधिकारिक सेवा खोलें",
        "requirements": "सत्यापित आवश्यकताएँ",
        "fee": "शुल्क जानकारी",
        "switch": "यह अनुरोध किसी दूसरी सत्यापित Sahayi सेवा से मेल खाता है। वर्तमान सेवा के तथ्यों का उपयोग किए बिना उस सेवा पर जाने के लिए उसे चुनें।",
        "address_clarify": "क्या आपका मतलब आधार का पता अपडेट करना है, या केरल पेंशन रिकॉर्ड के पते से जुड़ी मदद? Sahayi में आधार पता अपडेट की सत्यापित प्रक्रिया है, लेकिन पेंशन रिकॉर्ड का पता बदलने की अलग सत्यापित प्रक्रिया नहीं है; इसलिए मैं कोई अनुमान नहीं लगाऊँगा। संबंधित सत्यापित सेवा चुनें।",
        "pension_address_scope": "Sahayi की सत्यापित सूची में पेंशन रिकॉर्ड का पता बदलने की अलग प्रक्रिया नहीं है। आप सत्यापित सामान्य मार्गदर्शन के लिए केरल पेंशन सेवा चुनी रख सकते हैं, लेकिन Sahayi पता बदलने के चरण नहीं गढ़ेगा।",
        "invite": "बताइए कि आपको किस सरकारी सेवा में मदद चाहिए, जैसे आधार पता अपडेट या केरल वृद्धावस्था पेंशन।",
    },
    "ml": {
        "blocked": "ഈ സന്ദേശത്തിൽ വ്യക്തിയെ തിരിച്ചറിയുന്ന വിവരങ്ങൾ ഉണ്ടായേക്കാം; അതിനാൽ എനിക്ക് ഇത് ഉപയോഗിക്കാനാകില്ല. തിരിച്ചറിയൽ, ബന്ധപ്പെടൽ, വിലാസം, രേഖാ വിവരങ്ങൾ നീക്കി വീണ്ടും ശ്രമിക്കുക.",
        "unavailable": "Ask Sahayi AI ലഭ്യമല്ല. പരിശോധിച്ച നടപടികളും നിർണിത തയ്യാറെടുപ്പ് പരിശോധനയും തുടർന്നും ഉപയോഗിക്കാം.",
        "fallback": "AI മാർഗനിർദേശ ഘട്ടം പൂർത്തിയാക്കാനായില്ല. പരിശോധിച്ച നടപടിപ്പട്ടികയും നിർണിത പരിശോധനകളും ലഭ്യമാണ്.",
        "rate": "Ask Sahayi AIക്ക് ഇപ്പോൾ വളരെ അധികം അഭ്യർത്ഥനകളുണ്ട്. നിർണിത മാർഗനിർദേശം ഉപയോഗിക്കുക അല്ലെങ്കിൽ പിന്നീട് ശ്രമിക്കുക.",
        "disclaimer": "AI മാർഗനിർദേശം ഒരു പ്രോട്ടോടൈപ്പാണ്, തെറ്റാകാം, അർഹതാ തീരുമാനമോ അംഗീകാരമോ ഒരിക്കലും അല്ല. ഔദ്യോഗിക സ്രോതസ്സുകളാണ് പ്രാബല്യത്തിലുള്ളത്.",
        "clarify": "പരിശോധിച്ച മാർഗനിർദേശം മാത്രം ഉപയോഗിക്കാൻ പിന്തുണയുള്ള ഒരു സേവനം തിരഞ്ഞെടുക്കുക.",
        "view": "പരിശോധിച്ച നടപടി കാണുക",
        "readiness": "നിർണിത തയ്യാറെടുപ്പ് പരിശോധന തുടങ്ങുക",
        "checklist": "വ്യക്തിഗത ചെക്ക്‌ലിസ്റ്റ് നിർമ്മിക്കുക",
        "form": "കൃത്രിമ ഡെമോ വർക്ക്‌ഷീറ്റ് തയ്യാറാക്കുക",
        "official": "ഔദ്യോഗിക സേവനം തുറക്കുക",
        "requirements": "പരിശോധിച്ച ആവശ്യകതകൾ",
        "fee": "ഫീസ് വിവരം",
        "switch": "ഈ അഭ്യർത്ഥന മറ്റൊരു പരിശോധിച്ച Sahayi സേവനവുമായി പൊരുത്തപ്പെടുന്നതായി തോന്നുന്നു. നിലവിൽ തിരഞ്ഞെടുത്ത സേവനത്തിലെ വസ്തുതകൾ ഉപയോഗിക്കാതെ മാറാൻ ആ സേവനം തിരഞ്ഞെടുക്കുക.",
        "address_clarify": "ആധാർ വിലാസം പുതുക്കലാണോ, അതോ കേരള പെൻഷൻ രേഖയിലെ വിലാസവുമായി ബന്ധപ്പെട്ട സഹായമാണോ ഉദ്ദേശിക്കുന്നത്? Sahayiയിൽ പരിശോധിച്ച ആധാർ വിലാസ-പുതുക്കൽ നടപടിയുണ്ട്, പക്ഷേ പെൻഷൻ രേഖയിലെ വിലാസം മാറ്റാൻ പ്രത്യേകം പരിശോധിച്ച നടപടിയില്ല; അതിനാൽ ഞാൻ ഒന്നും അനുമാനിക്കില്ല. ബന്ധപ്പെട്ട പരിശോധിച്ച സേവനം തിരഞ്ഞെടുക്കുക.",
        "pension_address_scope": "Sahayiയുടെ പരിശോധിച്ച പട്ടികയിൽ പെൻഷൻ രേഖയിലെ വിലാസം മാറ്റാനുള്ള പ്രത്യേക നടപടിയില്ല. പരിശോധിച്ച പൊതുവായ മാർഗനിർദേശത്തിനായി കേരള പെൻഷൻ സേവനം തിരഞ്ഞെടുത്ത നിലയിൽ തുടരാം, എന്നാൽ Sahayi വിലാസമാറ്റ നടപടികൾ സൃഷ്ടിക്കില്ല.",
        "invite": "ആധാർ വിലാസം പുതുക്കൽ അല്ലെങ്കിൽ കേരള വയോജന പെൻഷൻ പോലുള്ള ഏത് സർക്കാർ സേവനത്തിലാണ് സഹായം വേണ്ടതെന്ന് പറയുക.",
    },
}


def _empty_selection(state: Literal["none", "clarification", "selected"] = "none") -> SelectionState:
    return SelectionState(state=state, service_id=None, choices=[])


def safe_response(
    locale: SupportedLocale,
    status: Literal["fallback", "blocked", "unavailable", "rate_limited"],
    *,
    choices: list[ServiceChoice] | None = None,
) -> AssistantTurnResponse:
    key = {"blocked": "blocked", "unavailable": "unavailable", "fallback": "fallback", "rate_limited": "rate"}[status]
    available_choices = choices or []
    return AssistantTurnResponse(
        status=status,
        locale=locale,
        message=_COPY[locale][key],
        selection=SelectionState(state="clarification" if available_choices else "none", service_id=None, choices=available_choices),
        fact_cards=[],
        sources=[],
        actions=[],
        tool_trace=[],
        disclaimer=_COPY[locale]["disclaimer"],
        fallback=True,
    )


def _local_invitation_response(locale: SupportedLocale) -> AssistantTurnResponse:
    return AssistantTurnResponse(
        status="ok",
        locale=locale,
        message=_COPY[locale]["invite"],
        selection=_empty_selection(),
        fact_cards=[],
        sources=[],
        actions=[],
        tool_trace=[],
        disclaimer=_COPY[locale]["disclaimer"],
        fallback=False,
    )


def _log_failure(
    reason: str,
    runtime: AgentRuntime,
    *,
    error: Exception | None = None,
    response_status: object = None,
    round_number: int | None = None,
    tool_calls: int | None = None,
    graph_node: AgentGraphNode | None = None,
    exposed_tools: tuple[str, ...] = (),
) -> None:
    """Log only operational metadata; never log prompts, output, arguments, IPs, or keys."""
    raw_status_code = getattr(error, "status_code", None)
    safe_status_code = raw_status_code if isinstance(raw_status_code, int) else None
    safe_response_status = response_status if response_status in {"completed", "failed", "in_progress", "incomplete"} else None
    provider_error_type = _safe_provider_error_field_value(error, "type")
    provider_error_code = _safe_provider_error_field_value(error, "code")
    provider_error_param = _safe_provider_error_field_value(error, "param")
    failed_generation_present = _failed_generation_present(error)
    logger.warning(
        "assistant_turn_failed reason=%s provider=%s model=%s status_code=%s exception_type=%s "
        "provider_error_type=%s provider_error_code=%s provider_error_param=%s "
        "failed_generation_present=%s graph_node=%s exposed_tool_count=%s exposed_tools=%s "
        "response_status=%s round=%s tool_calls=%s",
        reason,
        runtime.settings.agent_provider,
        runtime.settings.agent_model,
        safe_status_code,
        _safe_exception_type(error),
        provider_error_type,
        provider_error_code,
        provider_error_param,
        failed_generation_present,
        graph_node,
        len(exposed_tools),
        ",".join(exposed_tools),
        safe_response_status,
        round_number,
        tool_calls,
    )


def _failed_generation_present(error: Exception | None) -> bool:
    """Report only whether Groq supplied failed generation metadata, never its contents."""
    if error is None:
        return False
    body = getattr(error, "body", None)
    if not isinstance(body, dict):
        return False
    details = body.get("error", body)
    return isinstance(details, dict) and "failed_generation" in details


def _safe_provider_error_field_value(error: Exception | None, field: str) -> str | None:
    """Extract only bounded provider classification fields, never a content-bearing message."""
    if error is None:
        return None
    body = getattr(error, "body", None)
    if not isinstance(body, dict):
        return None
    details = body.get("error", body)
    if not isinstance(details, dict):
        return None
    value = details.get(field)
    if not isinstance(value, str):
        return None
    if field == "type":
        return value if value in _SAFE_PROVIDER_ERROR_TYPES else None
    if field == "code":
        return value if value in _SAFE_PROVIDER_ERROR_CODES else None
    if field == "param":
        return value if _SAFE_PROVIDER_ERROR_PARAM.fullmatch(value) is not None else None
    return None


def _safe_exception_type(error: Exception | None) -> str | None:
    if error is None:
        return None
    exception_type = type(error).__name__
    return exception_type if exception_type in _SAFE_EXCEPTION_TYPES else None


def _provider_failure_reason(error: Exception) -> str:
    status_code = getattr(error, "status_code", None)
    if status_code == 400:
        return "provider_bad_request"
    if status_code == 401:
        return "provider_authentication_error"
    if status_code == 403:
        return "provider_permission_error"
    if status_code == 408 or isinstance(error, TimeoutError) or type(error).__name__ == "APITimeoutError":
        return "provider_timeout"
    if status_code == 429:
        return "provider_rate_limit"
    if isinstance(status_code, int) and status_code >= 500:
        return "provider_server_error"
    return "provider_api_error"


def _service_choice(loaded: LoadedProcedure, locale: SupportedLocale) -> ServiceChoice:
    return ServiceChoice(
        service_id=loaded.pack.service_id,
        title=localized_text(loaded.pack, locale, "title", loaded.pack.title["en"]),
    )


def _catalogue_clarification(
    locale: SupportedLocale,
    registry: dict[str, LoadedProcedure],
    service_ids: list[str],
    message_key: Literal["switch", "address_clarify", "pension_address_scope"],
) -> AssistantTurnResponse:
    choices = [_service_choice(registry[service_id], locale) for service_id in service_ids if service_id in registry]
    return AssistantTurnResponse(
        status="ok",
        locale=locale,
        message=_COPY[locale][message_key],
        selection=SelectionState(state="clarification", service_id=None, choices=choices),
        fact_cards=[],
        sources=[],
        actions=[],
        tool_trace=[],
        disclaimer=_COPY[locale]["disclaimer"],
        fallback=False,
    )


def _normalise_intent(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).split())


_ADDRESS_TERMS = ("address", "पता", "വിലാസ")
_CHANGE_TERMS = ("change", "update", "correct", "बदल", "अपडेट", "सुधार", "മാറ്റ", "പുതുക്ക", "തിരുത്ത")
_AADHAAR_TERMS = ("aadhaar", "aadhar", "आधार", "ആധാർ", "ആധാര്")
_PENSION_TERMS = ("pension", "sevana", "पेंशन", "पेन्शन", "പെൻഷൻ", "പെന്‍ഷന്")
_GREETING_TERMS = {
    "hi", "hello", "hey", "namaste", "namaskar", "नमस्ते", "नमस्कार", "ഹലോ", "നമസ്കാരം",
}
_READINESS_TERMS = ("ready", "readiness", "eligible", "पात्र", "तैयार", "അർഹ", "തയ്യാർ")
_PREPARATION_TERMS = ("checklist", "worksheet", "form", "prepare", "चेकलिस्ट", "फॉर्म", "तैयार", "ചെക്ക്", "ഫോം", "തയ്യാർ")
_OFFICIAL_TERMS = ("official", "handoff", "apply", "open service", "आधिकारिक", "आवेदन", "ഔദ്യോഗിക", "അപേക്ഷ")


def _is_greeting_or_low_information(value: str) -> bool:
    normalized = _normalise_intent(value)
    if not normalized or normalized in {_normalise_intent(term) for term in _GREETING_TERMS}:
        return True
    compact = normalized.replace(" ", "")
    if len(compact) <= 2:
        return True
    if compact.isascii() and compact.isalpha() and len(compact) <= 16:
        vowels = sum(character in "aeiouy" for character in compact)
        if vowels == 0:
            return True
    return False


def _select_graph_node(
    request: AssistantTurnRequest,
    registry: dict[str, LoadedProcedure],
) -> AgentGraphNode:
    """Choose the provider phase only from already validated application state."""
    if request.demo_status_id is not None:
        return "explanation_status"
    if request.service_id not in registry:
        return "safety_intent"
    normalized = _normalise_intent(request.message)
    if any(term in normalized for term in _OFFICIAL_TERMS):
        return "official_handoff"
    try:
        readiness = evaluate_readiness(registry[request.service_id], request.readiness_answers, locale=request.locale)
    except ReadinessInputError:
        return "readiness_interview"
    if request.synthetic_persona_id is not None or (
        readiness.complete and any(term in normalized for term in _PREPARATION_TERMS)
    ):
        return "automatic_preparation"
    if request.readiness_answers or any(term in normalized for term in _READINESS_TERMS):
        return "readiness_interview"
    return "procedure_routing"


def _catalogue_route(
    request: AssistantTurnRequest,
    registry: dict[str, LoadedProcedure],
) -> AssistantTurnResponse | None:
    """Handle only catalogue-backed cross-service signals before calling the provider."""
    if request.service_id is None:
        return None
    normalized = _normalise_intent(request.message)
    address_change = any(term in normalized for term in _ADDRESS_TERMS) and any(term in normalized for term in _CHANGE_TERMS)
    aadhaar_id = "uidai-aadhaar-address-update"
    pension_id = "kerala-ign-oap"
    has_aadhaar_qualifier = any(term in normalized for term in _AADHAAR_TERMS)
    has_pension_qualifier = any(term in normalized for term in _PENSION_TERMS)

    if (
        request.service_id == pension_id
        and address_change
        and not has_aadhaar_qualifier
        and not has_pension_qualifier
        and aadhaar_id in registry
        and pension_id in registry
    ):
        return _catalogue_clarification(request.locale, registry, [aadhaar_id, pension_id], "address_clarify")
    if address_change and has_aadhaar_qualifier and has_pension_qualifier and aadhaar_id in registry and pension_id in registry:
        return _catalogue_clarification(request.locale, registry, [aadhaar_id, pension_id], "address_clarify")
    if address_change and has_pension_qualifier and pension_id in registry:
        return _catalogue_clarification(request.locale, registry, [pension_id], "pension_address_scope")

    candidates: list[str] = []
    for service_id, loaded in registry.items():
        if service_id == request.service_id:
            continue
        phrases = summarize_procedure(loaded, locale=request.locale).intent_phrases
        if any(_normalise_intent(phrase) in normalized for phrase in phrases if _normalise_intent(phrase)):
            candidates.append(service_id)
    if address_change and has_aadhaar_qualifier and aadhaar_id in registry and aadhaar_id != request.service_id:
        candidates.append(aadhaar_id)
    candidates = list(dict.fromkeys(candidates))
    if len(candidates) == 1:
        return _catalogue_clarification(request.locale, registry, candidates, "switch")
    if len(candidates) > 1:
        return _catalogue_clarification(request.locale, registry, candidates, "switch")
    return None


async def run_assistant_turn(
    request: AssistantTurnRequest,
    registry: dict[str, LoadedProcedure],
    runtime: AgentRuntime,
    client_address: str,
    *,
    graph_node: AgentGraphNode | None = None,
) -> AssistantTurnResponse:
    history_text = [message.content for message in request.history]
    if conversation_contains_high_risk_pii(request.message, history_text):
        return safe_response(request.locale, "blocked")
    if _is_greeting_or_low_information(request.message):
        return _local_invitation_response(request.locale)
    if not runtime.available:
        if not runtime.settings.agent_enabled:
            reason = "agent_disabled"
        elif not runtime.settings.agent_configuration_valid:
            reason = "invalid_provider_or_model_configuration"
        else:
            reason = "missing_provider_credential"
        _log_failure(reason, runtime)
        return safe_response(request.locale, "unavailable")
    catalogue_response = _catalogue_route(request, registry)
    if catalogue_response is not None:
        return catalogue_response
    key = runtime.rate_limiter.client_key(client_address)
    if not await runtime.rate_limiter.allow(key):
        _log_failure("client_rate_limit", runtime)
        return safe_response(request.locale, "rate_limited")

    try:
        async with runtime.semaphore:
            return await _provider_turn(
                request,
                registry,
                runtime,
                graph_node=graph_node or _select_graph_node(request, registry),
            )
    except Exception as error:
        _log_failure("internal_turn_processing_error", runtime, error=error)
        return safe_response(request.locale, "fallback")


async def _provider_turn(
    request: AssistantTurnRequest,
    registry: dict[str, LoadedProcedure],
    runtime: AgentRuntime,
    *,
    graph_node: AgentGraphNode,
) -> AssistantTurnResponse:
    if request.service_id is not None and request.service_id not in registry:
        return _clarification_response(request.locale, registry, [])
    client = runtime.get_client()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _instructions(request.locale, request.service_id, request.demo_status_id)},
        *[
            {"role": message.role, "content": message.content} for message in request.history
        ],
        {"role": "user", "content": request.message},
    ]
    trace: list[str] = []
    tool_calls = 0
    selected_id = request.service_id
    explained_status_id: DemoStatusId | None = None
    exposed_tools = NODE_TOOL_NAMES[graph_node]

    for round_index in range(runtime.settings.agent_max_rounds):
        round_number = round_index + 1
        if not await runtime.request_budget.take():
            _log_failure("process_request_budget_exhausted", runtime, round_number=round_number, tool_calls=tool_calls)
            return safe_response(request.locale, "fallback")
        try:
            messages[0] = {
                "role": "system",
                "content": _instructions(request.locale, selected_id, request.demo_status_id),
            }
            response = await client.chat.completions.create(
                **_provider_request(
                    registry,
                    runtime,
                    messages,
                    graph_node=graph_node,
                    final=bool(trace),
                )
            )
        except Exception as error:
            _log_failure(
                _provider_failure_reason(error),
                runtime,
                error=error,
                round_number=round_number,
                tool_calls=tool_calls,
                graph_node=graph_node,
                exposed_tools=exposed_tools if not trace else (),
            )
            status = "rate_limited" if getattr(error, "status_code", None) == 429 else "fallback"
            return safe_response(request.locale, status)
        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or len(choices) != 1:
            _log_failure("malformed_provider_response", runtime, round_number=round_number, tool_calls=tool_calls)
            return safe_response(request.locale, "fallback")
        message = getattr(choices[0], "message", None)
        if message is None:
            _log_failure("malformed_provider_response", runtime, round_number=round_number, tool_calls=tool_calls)
            return safe_response(request.locale, "fallback")
        raw_calls = getattr(message, "tool_calls", None)
        if raw_calls is None:
            calls: list[Any] = []
        elif isinstance(raw_calls, list):
            calls = raw_calls
        else:
            _log_failure("malformed_tool_call", runtime, round_number=round_number, tool_calls=tool_calls)
            return safe_response(request.locale, "fallback")
        if not calls:
            output_text = getattr(message, "content", None)
            if not isinstance(output_text, str) or not output_text.strip():
                _log_failure("missing_model_output_text", runtime, round_number=round_number, tool_calls=tool_calls)
                return safe_response(request.locale, "fallback")
            try:
                parsed = AgentModelOutput.model_validate_json(output_text)
            except ValidationError as error:
                error_types = {item["type"] for item in error.errors(include_url=False)}
                reason = "model_output_invalid_json" if "json_invalid" in error_types else "model_output_schema_invalid"
                _log_failure(reason, runtime, error=error, round_number=round_number, tool_calls=tool_calls)
                return safe_response(request.locale, "fallback")
            if parsed.service_id is not None and parsed.service_id not in registry:
                _log_failure("unknown_model_service_id", runtime, round_number=round_number, tool_calls=tool_calls)
                return safe_response(request.locale, "fallback")
            if (
                graph_node != "safety_intent"
                and selected_id is not None
                and parsed.service_id not in {None, selected_id}
            ):
                _log_failure("model_service_scope_mismatch", runtime, round_number=round_number, tool_calls=tool_calls)
                return safe_response(request.locale, "fallback")
            if parsed.service_id in registry:
                selected_id = parsed.service_id
            return _assemble_response(request.locale, registry, parsed, selected_id, trace, explained_status_id)

        reconstructed_calls: list[dict[str, Any]] = []
        tool_messages: list[dict[str, Any]] = []
        for call in calls:
            tool_calls += 1
            if tool_calls > runtime.settings.agent_max_tool_calls:
                _log_failure("tool_call_budget_exhausted", runtime, round_number=round_number, tool_calls=tool_calls)
                return safe_response(request.locale, "fallback")
            call_id = getattr(call, "id", None)
            function = getattr(call, "function", None)
            name = getattr(function, "name", None)
            arguments = getattr(function, "arguments", None)
            if not isinstance(call_id, str) or _TOOL_CALL_ID.fullmatch(call_id) is None:
                _log_failure("malformed_tool_call", runtime, round_number=round_number, tool_calls=tool_calls)
                return safe_response(request.locale, "fallback")
            if name not in exposed_tools or trace:
                _log_failure("unknown_tool_call", runtime, round_number=round_number, tool_calls=tool_calls)
                return safe_response(request.locale, "fallback")
            if not isinstance(arguments, str):
                _log_failure("malformed_tool_call", runtime, round_number=round_number, tool_calls=tool_calls)
                return safe_response(request.locale, "fallback")
            bound_arguments = _bind_provider_tool_arguments(name, arguments, request)
            if bound_arguments is None:
                _log_failure(
                    "tool_argument_validation_failed",
                    runtime,
                    round_number=round_number,
                    tool_calls=tool_calls,
                    graph_node=graph_node,
                    exposed_tools=exposed_tools,
                )
                return safe_response(request.locale, "fallback")
            tool_output, used_service, used_status = _execute_tool(name, bound_arguments, registry)
            if tool_output == '{"error": "Invalid tool request"}':
                _log_failure("tool_argument_validation_failed", runtime, round_number=round_number, tool_calls=tool_calls)
                return safe_response(request.locale, "fallback")
            if name == "explain_simulated_status" and used_status != request.demo_status_id:
                _log_failure("demo_status_tool_scope_mismatch", runtime, round_number=round_number, tool_calls=tool_calls)
                return safe_response(request.locale, "fallback")
            if used_service is not None:
                selected_id = used_service
            if used_status is not None:
                explained_status_id = used_status
            trace.append(name)
            reconstructed_calls.append({
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            })
            tool_messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": name,
                "content": tool_output,
            })
        messages.append({"role": "assistant", "tool_calls": reconstructed_calls})
        messages.extend(tool_messages)
    _log_failure("tool_round_budget_exhausted", runtime, round_number=runtime.settings.agent_max_rounds, tool_calls=tool_calls)
    return safe_response(request.locale, "fallback")


def _instructions(locale: SupportedLocale, service_id: str | None, demo_status_id: DemoStatusId | None) -> str:
    return (
        "You are Sahayi's concise prototype guide. Respond in the requested locale. "
        "Never invent procedure facts, fees, eligibility, URLs, approval, submission, form filling, real tracking, or monitoring. "
        "A simulated status is fictional and may be explained only through explain_simulated_status; never request or accept a real reference number. "
        "Use only the supplied local functions for facts and use their exact service IDs. Ask for service clarification when needed. "
        "Do not request or repeat identifiers, contact details, addresses, OTPs, document contents, or files. "
        "Return a single JSON object without Markdown and with exactly these fields: "
        "guidance_message (string), selection_state (none, clarification, or selected), "
        "service_id (a supplied service ID or null), and action_ids (an array using only: "
        "view-procedure, start-readiness, build-checklist, prepare-synthetic-form, or open-official-service). "
        f"Locale: {locale}. Current validated service: {service_id or 'none'}. Current validated demo status: {demo_status_id or 'none'}."
    )


def _strict_tool(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {"type": "object", "properties": properties, "required": required, "additionalProperties": False},
    }


def _normalise_groq_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Validate and copy only the deliberately simple provider schema subset."""
    if not isinstance(schema, dict):
        raise ValueError("Provider schema must be an object")

    def visit(value: Any) -> Any:
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        if any(keyword in value for keyword in ("anyOf", "oneOf", "maxItems")):
            raise ValueError("Unsupported provider schema keyword")
        schema_type = value.get("type")
        if isinstance(schema_type, list):
            raise ValueError("Unsupported provider schema union")
        if schema_type == "null":
            raise ValueError("Unsupported provider nullable schema")
        if schema_type is not None and schema_type not in _JSON_SCHEMA_TYPES:
            raise ValueError("Unsupported provider schema type")
        return {key: visit(item) for key, item in value.items()}

    return visit(deepcopy(schema))


def _provider_tool_definitions(
    registry: dict[str, LoadedProcedure],
    graph_node: AgentGraphNode = "safety_intent",
) -> list[dict[str, Any]]:
    return _provider_tool_definitions_for_node(registry, graph_node)


def _provider_tool_definitions_for_node(
    registry: dict[str, LoadedProcedure],
    graph_node: AgentGraphNode,
) -> list[dict[str, Any]]:
    """Expose only the node allowlist with state-bound, zero-argument schemas."""
    canonical_by_name = {tool["name"]: tool for tool in _tool_definitions(registry)}
    tools: list[dict[str, Any]] = []
    for name in NODE_TOOL_NAMES[graph_node]:
        canonical = canonical_by_name[name]
        tool = {
            "type": "function",
            "function": {
                "name": name,
                "description": canonical["description"],
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }
        _validate_provider_tool(tool)
        tools.append(tool)
    if len(tools) > 3:
        raise ValueError("Provider tool exposure exceeds node limit")
    return tools


def _validate_provider_tool(tool: dict[str, Any]) -> None:
    """Fail closed before transport if a generated Chat Completions tool drifts."""
    if set(tool) != {"type", "function"} or tool.get("type") != "function":
        raise ValueError("Invalid provider tool envelope")
    function = tool.get("function")
    if not isinstance(function, dict) or set(function) != {"name", "description", "parameters"}:
        raise ValueError("Invalid provider function")
    if function.get("name") not in TOOL_NAMES or not isinstance(function.get("description"), str):
        raise ValueError("Invalid provider function metadata")

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        if any(keyword in value for keyword in ("strict", "maxItems", "anyOf", "oneOf")):
            raise ValueError("Unsupported provider schema keyword")
        schema_type = value.get("type")
        if isinstance(schema_type, list):
            raise ValueError("Unsupported provider schema type union")
        if schema_type == "null":
            raise ValueError("Unsupported provider nullable schema")
        if schema_type == "object":
            properties = value.get("properties")
            required = value.get("required")
            if (
                not isinstance(properties, dict)
                or required != list(properties)
                or value.get("additionalProperties") is not False
            ):
                raise ValueError("Provider objects must require exactly their declared properties")
        for item in value.values():
            visit(item)

    visit(function["parameters"])


def _provider_request(
    registry: dict[str, LoadedProcedure],
    runtime: AgentRuntime,
    messages: list[dict[str, Any]],
    *,
    graph_node: AgentGraphNode = "safety_intent",
    final: bool = False,
) -> dict[str, Any]:
    """Build the sole provider-bound request without mutating canonical schemas or input state."""
    request: dict[str, Any] = {
        "model": runtime.settings.agent_model,
        "messages": deepcopy(messages),
        "tool_choice": "none" if final or not NODE_TOOL_NAMES[graph_node] else "auto",
        "stream": False,
        "temperature": 0,
        "max_completion_tokens": runtime.settings.agent_max_output_tokens,
    }
    if not final and NODE_TOOL_NAMES[graph_node]:
        request["tools"] = _provider_tool_definitions_for_node(registry, graph_node)
        request["parallel_tool_calls"] = False
    return request


def _tool_definitions(registry: dict[str, LoadedProcedure] | None = None) -> list[dict[str, Any]]:
    locale = {"type": "string", "enum": ["en", "hi", "ml"]}
    service = {"type": "string", "enum": sorted(registry) if registry is not None else ["uidai-aadhaar-address-update", "kerala-ign-oap"]}
    question_ids = sorted({
        question.question_id
        for loaded in (registry or {}).values()
        for question in loaded.pack.readiness.questions
    })
    answers = {
        "type": "array",
        "maxItems": 30,
        "items": {
            "type": "object",
            "properties": {
                "question_id": {"type": "string", "enum": question_ids},
                "value": {"type": ["boolean", "integer", "string"]},
            },
            "required": ["question_id", "value"],
            "additionalProperties": False,
        },
    }
    persona_ids = sorted({
        persona.persona_id
        for loaded in (registry or {}).values()
        for persona in (loaded.pack.assistance.personas if loaded.pack.assistance is not None else [])
    })
    status_ids = [status.value for status in DemoStatusId]
    return [
        _strict_tool("list_supported_services", "List only supported verified services.", {"locale": locale}, ["locale"]),
        _strict_tool("get_verified_procedure", "Get the verified procedure pack.", {"service_id": service, "locale": locale}, ["service_id", "locale"]),
        _strict_tool("get_readiness_questions", "Get the next deterministic readiness question.", {"service_id": service, "locale": locale, "answers": answers}, ["service_id", "locale", "answers"]),
        _strict_tool("evaluate_readiness", "Evaluate closed readiness answers deterministically.", {"service_id": service, "locale": locale, "answers": answers}, ["service_id", "locale", "answers"]),
        _strict_tool("build_personalized_checklist", "Build a cited deterministic checklist.", {"service_id": service, "locale": locale, "answers": answers}, ["service_id", "locale", "answers"]),
        _strict_tool("prepare_synthetic_form_assistance", "Prepare a synthetic, non-submittable worksheet.", {"service_id": service, "locale": locale, "persona_id": {"type": ["string", "null"], "enum": [*persona_ids, None]}}, ["service_id", "locale", "persona_id"]),
        _strict_tool("explain_simulated_status", "Explain only a validated fictional demo status; never look up a real application.", {"service_id": service, "locale": locale, "status_id": {"type": "string", "enum": status_ids}}, ["service_id", "locale", "status_id"]),
    ]


def _bind_provider_tool_arguments(
    name: str,
    arguments: str,
    request: AssistantTurnRequest,
) -> str | None:
    """Replace the model's empty object with canonical values from validated state."""
    try:
        supplied = json.loads(arguments)
    except (json.JSONDecodeError, TypeError):
        return None
    if supplied != {}:
        return None

    canonical: dict[str, Any] = {"locale": request.locale}
    if name == "list_supported_services":
        return json.dumps(canonical, ensure_ascii=False)
    if request.service_id is None:
        return None
    canonical["service_id"] = request.service_id
    if name in {
        "get_readiness_questions",
        "evaluate_readiness",
        "build_personalized_checklist",
    }:
        canonical["answers"] = [
            {"question_id": question_id, "value": value}
            for question_id, value in request.readiness_answers.items()
        ]
    elif name == "prepare_synthetic_form_assistance":
        canonical["persona_id"] = request.synthetic_persona_id
    elif name == "explain_simulated_status":
        if request.demo_status_id is None:
            return None
        canonical["status_id"] = request.demo_status_id.value
    elif name != "get_verified_procedure":
        return None
    return json.dumps(canonical, ensure_ascii=False)


def _execute_tool(name: str, arguments: str, registry: dict[str, LoadedProcedure]) -> tuple[str, str | None, DemoStatusId | None]:
    def readiness_answers(value: object) -> dict[str, AnswerValue]:
        if not isinstance(value, list) or len(value) > 30:
            raise ValueError
        result: dict[str, AnswerValue] = {}
        for item in value:
            if not isinstance(item, dict) or set(item) != {"question_id", "value"}:
                raise ValueError
            question_id = item["question_id"]
            answer = item["value"]
            if not isinstance(question_id, str) or question_id in result or type(answer) not in {bool, int, str}:
                raise ValueError
            result[question_id] = answer
        return result

    try:
        values = json.loads(arguments)
        if not isinstance(values, dict):
            raise ValueError
        input_models: dict[str, type[StrictModel]] = {
            "list_supported_services": ToolServiceListInput,
            "get_verified_procedure": ToolProcedureInput,
            "get_readiness_questions": ToolReadinessInput,
            "evaluate_readiness": ToolReadinessInput,
            "build_personalized_checklist": ToolReadinessInput,
            "prepare_synthetic_form_assistance": ToolPersonaInput,
            "explain_simulated_status": ToolStatusInput,
        }
        input_model = input_models.get(name)
        if input_model is None:
            raise ValueError
        values = input_model.model_validate(values).model_dump(mode="json")
        locale = values.get("locale")
        if locale not in {"en", "hi", "ml"}:
            raise ValueError
        if name == "list_supported_services":
            result = [summarize_procedure(loaded, locale=locale).model_dump(mode="json") for loaded in registry.values()]
            return json.dumps(result, ensure_ascii=False), None, None
        service_id = values.get("service_id")
        if service_id not in registry:
            raise ValueError
        loaded = registry[service_id]
        if name == "get_verified_procedure":
            result = detail_procedure(loaded, locale=locale)
        elif name in {"get_readiness_questions", "evaluate_readiness"}:
            answers = readiness_answers(values.get("answers"))
            result = evaluate_readiness(loaded, answers, locale=locale)
        elif name == "build_personalized_checklist":
            answers = readiness_answers(values.get("answers"))
            result = build_personalized_checklist(loaded, answers, locale=locale)
        elif name == "prepare_synthetic_form_assistance":
            result = prepare_synthetic_form_assistance(loaded, values.get("persona_id"), locale=locale)
        elif name == "explain_simulated_status":
            status_id = DemoStatusId(values.get("status_id"))
            result = explain_simulated_status(loaded, status_id, locale=locale)
            return json.dumps(result.model_dump(mode="json"), ensure_ascii=False), service_id, status_id
        else:
            raise ValueError
        return json.dumps(result.model_dump(mode="json"), ensure_ascii=False), service_id, None
    except (ValueError, ValidationError, ReadinessInputError, TypeError):
        return json.dumps({"error": "Invalid tool request"}), None, None


def _clarification_response(locale: SupportedLocale, registry: dict[str, LoadedProcedure], trace: list[str]) -> AssistantTurnResponse:
    choices = [_service_choice(loaded, locale) for loaded in registry.values()]
    return AssistantTurnResponse(
        status="ok",
        locale=locale,
        message=_COPY[locale]["clarify"],
        selection=SelectionState(state="clarification", service_id=None, choices=choices),
        fact_cards=[],
        sources=[],
        actions=[],
        tool_trace=trace,
        disclaimer=_COPY[locale]["disclaimer"],
        fallback=False,
    )


def _assemble_response(
    locale: SupportedLocale,
    registry: dict[str, LoadedProcedure],
    model_output: AgentModelOutput,
    service_id: str | None,
    trace: list[str],
    explained_status_id: DemoStatusId | None = None,
) -> AssistantTurnResponse:
    if _UNSAFE_MODEL_PROSE.search(model_output.guidance_message):
        logger.warning("assistant_turn_failed reason=unsafe_model_prose")
        return safe_response(locale, "fallback")
    if model_output.service_id is not None and model_output.service_id not in registry:
        return _clarification_response(locale, registry, trace)
    if model_output.selection_state == "clarification" or service_id not in registry:
        return _clarification_response(locale, registry, trace)
    loaded = registry[service_id]
    pack = loaded.pack
    requirements = " ".join(localized_text(pack, locale, f"requirement.{fact.fact_id}", fact.text) for fact in pack.requirements)
    cards = [
        FactCard(card_id="verified-requirements", title=_COPY[locale]["requirements"], text=requirements, source_ids=pack.provenance["requirements"]),
        FactCard(card_id="fee-information", title=_COPY[locale]["fee"], text=localized_text(pack, locale, "fee.display-message", pack.fee.display_message), source_ids=pack.fee.source_ids),
    ]
    if explained_status_id is not None:
        status = explain_simulated_status(loaded, explained_status_id, locale=locale)
        cards.append(
            FactCard(
                card_id=f"demo-{status.status_id.value}",
                title=status.title,
                text=f"{status.explanation} {status.next_action}",
                source_ids=status.source_ids,
            )
        )
    source_ids = {source_id for card in cards for source_id in card.source_ids}
    action_labels = {
        "view-procedure": "view",
        "start-readiness": "readiness",
        "build-checklist": "checklist",
        "prepare-synthetic-form": "form",
        "open-official-service": "official",
    }
    requested = [action_id for action_id in model_output.action_ids if action_id in ACTION_IDS]
    if not requested:
        requested = ["view-procedure", "start-readiness"]
    actions = [AgentAction(action_id=action_id, label=_COPY[locale][action_labels[action_id]], service_id=service_id) for action_id in dict.fromkeys(requested)]
    return AssistantTurnResponse(
        status="ok",
        locale=locale,
        message=model_output.guidance_message,
        selection=SelectionState(state="selected", service_id=service_id, choices=[]),
        fact_cards=cards,
        sources=localized_sources(pack, locale, source_ids),
        actions=actions,
        tool_trace=trace,
        disclaimer=_COPY[locale]["disclaimer"],
        fallback=False,
    )

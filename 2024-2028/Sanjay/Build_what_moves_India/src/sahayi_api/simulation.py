from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from sahayi_api.procedures import Identifier, LoadedProcedure, ShortText, SourceId, StrictModel, SupportedLocale


DemoReference = Annotated[str, StringConstraints(pattern=r"^DEMO-[A-Z]+-[A-Z]+$", min_length=12, max_length=40)]


class DemoScenarioId(StrEnum):
    NORMAL = "normal-completion"
    ACTION_REQUIRED = "action-required"


class DemoStatusId(StrEnum):
    PREPARATION_COMPLETED = "preparation-completed"
    DEMO_SUBMITTED = "demo-submitted"
    SIMULATED_REVIEW = "simulated-review"
    ACTION_REQUIRED = "action-required"
    DEMO_COMPLETED = "demo-completed"


class TimelineState(StrEnum):
    COMPLETE = "complete"
    CURRENT = "current"
    UPCOMING = "upcoming"


class DemoSubmissionRequest(StrictModel):
    persona_id: Identifier
    scenario_id: DemoScenarioId


class DemoStatusRequest(StrictModel):
    persona_id: Identifier
    scenario_id: DemoScenarioId
    demo_reference: DemoReference
    status_id: DemoStatusId


class DemoStatusItem(StrictModel):
    status_id: DemoStatusId
    title: ShortText
    explanation: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=900)]
    state: TimelineState
    simulated_time_label: ShortText
    next_action: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    source_ids: Annotated[list[SourceId], Field(max_length=6)]


class DemoJourneyResponse(StrictModel):
    locale: SupportedLocale
    service_id: Identifier
    persona_id: Identifier
    scenario_id: DemoScenarioId
    scenario_title: ShortText
    demo_reference: DemoReference
    current_status_id: DemoStatusId
    statuses: Annotated[list[DemoStatusItem], Field(min_length=4, max_length=5)]
    can_advance: bool
    synthetic: Literal[True]
    disclosure: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=900)]
    disclaimer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=900)]


_SEQUENCES = {
    DemoScenarioId.NORMAL: [
        DemoStatusId.PREPARATION_COMPLETED,
        DemoStatusId.DEMO_SUBMITTED,
        DemoStatusId.SIMULATED_REVIEW,
        DemoStatusId.DEMO_COMPLETED,
    ],
    DemoScenarioId.ACTION_REQUIRED: [
        DemoStatusId.PREPARATION_COMPLETED,
        DemoStatusId.DEMO_SUBMITTED,
        DemoStatusId.SIMULATED_REVIEW,
        DemoStatusId.ACTION_REQUIRED,
        DemoStatusId.DEMO_COMPLETED,
    ],
}


_COPY = {
    "en": {
        "scenario-normal": "Normal demo completion",
        "scenario-action": "Demo with action required",
        "disclosure": "Simulation only: no application is submitted, no government system is contacted, and only bundled synthetic data is used. This demo disappears when the Sahayi session ends.",
        "disclaimer": "Synthetic status demonstration only. This is not a government acknowledgement, application status, approval, submission, or tracking service.",
        "preparation-completed-title": "Preparation completed",
        "preparation-completed-explanation": "The bundled synthetic checklist and worksheet are ready for this demonstration.",
        "preparation-completed-action": "Review the synthetic preparation material, then advance the demo deliberately.",
        "demo-submitted-title": "Demo submitted",
        "demo-submitted-explanation": "Sahayi changed only the local simulation state. Nothing was transmitted to a government system.",
        "demo-submitted-action": "Advance to the simulated review when you are ready.",
        "simulated-review-title": "Simulated review",
        "simulated-review-explanation": "This fictional review illustrates a possible status step without checking or predicting a real application.",
        "simulated-review-action": "Choose the next simulated step deliberately.",
        "action-required-title": "Action required",
        "action-required-explanation": "The fictional scenario asks the demo citizen to review preparation information. It does not represent an official request.",
        "action-required-action": "Return to the cited preparation guidance, then advance the simulation.",
        "demo-completed-title": "Demo completed",
        "demo-completed-explanation": "The local synthetic scenario is complete. No official outcome or approval has been produced.",
        "demo-completed-action": "End the session to clear the synthetic reference and all in-memory state.",
        "step": "SIMULATED — step {current} of {total}",
    },
    "hi": {
        "scenario-normal": "सामान्य डेमो पूर्णता",
        "scenario-action": "कार्रवाई-आवश्यक डेमो",
        "disclosure": "केवल सिमुलेशन: कोई आवेदन जमा नहीं होता, किसी सरकारी प्रणाली से संपर्क नहीं किया जाता और केवल बंडल किया गया कृत्रिम डेटा उपयोग होता है। Sahayi सत्र समाप्त होने पर यह डेमो मिट जाता है।",
        "disclaimer": "केवल कृत्रिम स्थिति प्रदर्शन। यह सरकारी पावती, आवेदन स्थिति, स्वीकृति, जमा करने या ट्रैकिंग की सेवा नहीं है।",
        "preparation-completed-title": "तैयारी पूरी हुई",
        "preparation-completed-explanation": "इस प्रदर्शन के लिए बंडल की गई कृत्रिम चेकलिस्ट और वर्कशीट तैयार हैं।",
        "preparation-completed-action": "कृत्रिम तैयारी सामग्री देखें और फिर जानबूझकर डेमो आगे बढ़ाएँ।",
        "demo-submitted-title": "डेमो जमा हुआ",
        "demo-submitted-explanation": "Sahayi ने केवल स्थानीय सिमुलेशन स्थिति बदली। किसी सरकारी प्रणाली को कुछ नहीं भेजा गया।",
        "demo-submitted-action": "तैयार होने पर सिमुलेटेड समीक्षा पर जाएँ।",
        "simulated-review-title": "सिमुलेटेड समीक्षा",
        "simulated-review-explanation": "यह काल्पनिक समीक्षा वास्तविक आवेदन जाँचे या अनुमान लगाए बिना एक संभावित स्थिति चरण दिखाती है।",
        "simulated-review-action": "अगला सिमुलेटेड चरण जानबूझकर चुनें।",
        "action-required-title": "कार्रवाई आवश्यक",
        "action-required-explanation": "काल्पनिक परिदृश्य डेमो नागरिक से तैयारी जानकारी देखने को कहता है। यह आधिकारिक अनुरोध नहीं है।",
        "action-required-action": "उद्धृत तैयारी मार्गदर्शन पर लौटें, फिर सिमुलेशन आगे बढ़ाएँ।",
        "demo-completed-title": "डेमो पूरा हुआ",
        "demo-completed-explanation": "स्थानीय कृत्रिम परिदृश्य पूरा हुआ। कोई आधिकारिक परिणाम या स्वीकृति नहीं बनी।",
        "demo-completed-action": "कृत्रिम संदर्भ और सभी इन-मेमोरी स्थिति मिटाने के लिए सत्र समाप्त करें।",
        "step": "सिमुलेटेड — चरण {current}/{total}",
    },
    "ml": {
        "scenario-normal": "സാധാരണ ഡെമോ പൂർത്തീകരണം",
        "scenario-action": "നടപടി ആവശ്യമായ ഡെമോ",
        "disclosure": "സിമുലേഷൻ മാത്രം: അപേക്ഷ സമർപ്പിക്കില്ല, സർക്കാർ സംവിധാനവുമായി ബന്ധപ്പെടില്ല, ബണ്ടിൽ ചെയ്ത കൃത്രിമ ഡാറ്റ മാത്രം ഉപയോഗിക്കും. Sahayi സെഷൻ അവസാനിക്കുമ്പോൾ ഈ ഡെമോ മായും.",
        "disclaimer": "കൃത്രിമ നില പ്രദർശനം മാത്രം. ഇത് സർക്കാർ അംഗീകാരരസീതോ അപേക്ഷാ നിലയോ അംഗീകാരമോ സമർപ്പണമോ ട്രാക്കിംഗ് സേവനമോ അല്ല.",
        "preparation-completed-title": "തയ്യാറെടുപ്പ് പൂർത്തിയായി",
        "preparation-completed-explanation": "ഈ പ്രദർശനത്തിനുള്ള ബണ്ടിൽ ചെയ്ത കൃത്രിമ ചെക്ക്‌ലിസ്റ്റും വർക്ക്‌ഷീറ്റും തയ്യാറാണ്.",
        "preparation-completed-action": "കൃത്രിമ തയ്യാറെടുപ്പ് വിവരങ്ങൾ പരിശോധിച്ച് ഡെമോ മനപ്പൂർവം മുന്നോട്ട് നീക്കുക.",
        "demo-submitted-title": "ഡെമോ സമർപ്പിച്ചു",
        "demo-submitted-explanation": "Sahayi പ്രാദേശിക സിമുലേഷൻ നില മാത്രം മാറ്റി. സർക്കാർ സംവിധാനത്തിലേക്ക് ഒന്നും അയച്ചിട്ടില്ല.",
        "demo-submitted-action": "തയ്യാറാകുമ്പോൾ സിമുലേറ്റഡ് പരിശോധനയിലേക്ക് നീങ്ങുക.",
        "simulated-review-title": "സിമുലേറ്റഡ് പരിശോധന",
        "simulated-review-explanation": "യഥാർത്ഥ അപേക്ഷ പരിശോധിക്കുകയോ പ്രവചിക്കുകയോ ചെയ്യാതെ ഒരു സാധ്യതാ നില ഈ സാങ്കൽപ്പിക പരിശോധന കാണിക്കുന്നു.",
        "simulated-review-action": "അടുത്ത സിമുലേറ്റഡ് ഘട്ടം മനപ്പൂർവം തിരഞ്ഞെടുക്കുക.",
        "action-required-title": "നടപടി ആവശ്യമാണ്",
        "action-required-explanation": "തയ്യാറെടുപ്പ് വിവരം പരിശോധിക്കാൻ ഡെമോ പൗരനോട് സാങ്കൽപ്പിക സാഹചര്യം ആവശ്യപ്പെടുന്നു. ഇത് ഔദ്യോഗിക അഭ്യർത്ഥനയല്ല.",
        "action-required-action": "ഉദ്ധരിച്ച തയ്യാറെടുപ്പ് മാർഗനിർദേശത്തിലേക്ക് മടങ്ങി സിമുലേഷൻ മുന്നോട്ട് നീക്കുക.",
        "demo-completed-title": "ഡെമോ പൂർത്തിയായി",
        "demo-completed-explanation": "പ്രാദേശിക കൃത്രിമ സാഹചര്യം പൂർത്തിയായി. ഔദ്യോഗിക ഫലമോ അംഗീകാരമോ ഉണ്ടായിട്ടില്ല.",
        "demo-completed-action": "കൃത്രിമ റഫറൻസും എല്ലാ ഇൻ-മെമ്മറി നിലയും മായ്ക്കാൻ സെഷൻ അവസാനിപ്പിക്കുക.",
        "step": "സിമുലേറ്റഡ് — ഘട്ടം {current}/{total}",
    },
}


def _persona_ids(loaded: LoadedProcedure) -> set[str]:
    assistance = loaded.pack.assistance
    return {persona.persona_id for persona in assistance.personas} if assistance is not None else set()


def demo_reference(loaded: LoadedProcedure, scenario_id: DemoScenarioId) -> str:
    service_label = "UIDAI" if loaded.pack.service_id == "uidai-aadhaar-address-update" else "KERALA"
    scenario_label = "NORMAL" if scenario_id is DemoScenarioId.NORMAL else "ACTION"
    return f"DEMO-{service_label}-{scenario_label}"


def _validate_request(loaded: LoadedProcedure, persona_id: str, scenario_id: DemoScenarioId, reference: str | None = None) -> None:
    if persona_id not in _persona_ids(loaded):
        raise ValueError("Unknown synthetic persona")
    if reference is not None and reference != demo_reference(loaded, scenario_id):
        raise ValueError("Invalid synthetic reference")


def _related_sources(loaded: LoadedProcedure, status_id: DemoStatusId) -> list[str]:
    if status_id in {DemoStatusId.PREPARATION_COMPLETED, DemoStatusId.ACTION_REQUIRED}:
        return list(dict.fromkeys(loaded.pack.provenance["required-documents"] + loaded.pack.provenance["steps"]))[:6]
    return []


def _build(
    loaded: LoadedProcedure,
    persona_id: str,
    scenario_id: DemoScenarioId,
    current_status_id: DemoStatusId,
    *,
    locale: SupportedLocale,
) -> DemoJourneyResponse:
    sequence = _SEQUENCES[scenario_id]
    if current_status_id not in sequence:
        raise ValueError("Status does not belong to the selected demo scenario")
    current_index = sequence.index(current_status_id)
    copy = _COPY[locale]
    statuses = []
    for index, status_id in enumerate(sequence):
        state = TimelineState.COMPLETE if index < current_index else TimelineState.CURRENT if index == current_index else TimelineState.UPCOMING
        key = status_id.value
        statuses.append(
            DemoStatusItem(
                status_id=status_id,
                title=copy[f"{key}-title"],
                explanation=copy[f"{key}-explanation"],
                state=state,
                simulated_time_label=copy["step"].format(current=index + 1, total=len(sequence)),
                next_action=copy[f"{key}-action"],
                source_ids=_related_sources(loaded, status_id),
            )
        )
    return DemoJourneyResponse(
        locale=locale,
        service_id=loaded.pack.service_id,
        persona_id=persona_id,
        scenario_id=scenario_id,
        scenario_title=copy["scenario-normal" if scenario_id is DemoScenarioId.NORMAL else "scenario-action"],
        demo_reference=demo_reference(loaded, scenario_id),
        current_status_id=current_status_id,
        statuses=statuses,
        can_advance=current_index < len(sequence) - 1,
        synthetic=True,
        disclosure=copy["disclosure"],
        disclaimer=copy["disclaimer"],
    )


def start_demo_submission(
    loaded: LoadedProcedure,
    request: DemoSubmissionRequest,
    *,
    locale: SupportedLocale = "en",
) -> DemoJourneyResponse:
    _validate_request(loaded, request.persona_id, request.scenario_id)
    return _build(loaded, request.persona_id, request.scenario_id, _SEQUENCES[request.scenario_id][0], locale=locale)


def get_demo_status(
    loaded: LoadedProcedure,
    request: DemoStatusRequest,
    *,
    locale: SupportedLocale = "en",
) -> DemoJourneyResponse:
    _validate_request(loaded, request.persona_id, request.scenario_id, request.demo_reference)
    return _build(loaded, request.persona_id, request.scenario_id, request.status_id, locale=locale)


def explain_simulated_status(
    loaded: LoadedProcedure,
    status_id: DemoStatusId,
    *,
    locale: SupportedLocale = "en",
) -> DemoStatusItem:
    copy = _COPY[locale]
    key = status_id.value
    return DemoStatusItem(
        status_id=status_id,
        title=copy[f"{key}-title"],
        explanation=copy[f"{key}-explanation"],
        state=TimelineState.CURRENT,
        simulated_time_label=copy["step"].format(current=1, total=1),
        next_action=copy[f"{key}-action"],
        source_ids=_related_sources(loaded, status_id),
    )

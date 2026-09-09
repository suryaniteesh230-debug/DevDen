from typing import Any, TypedDict
from uuid import uuid4


class CapabilityStatus(TypedDict, total=False):
    status: str
    reason: str
    details: dict[str, Any]


class AgentTraceEntry(TypedDict, total=False):
    agent: str
    status: str
    started_at: str
    completed_at: str
    duration_ms: float
    summary: str
    warnings: list[str]
    errors: list[str]
    capability_status: dict[str, CapabilityStatus]


class ClinicalState(TypedDict, total=False):
    # Workflow identity
    workflow_id: str
    patient_id: str
    encounter_id: str

    # Patient context
    patient: dict[str, Any] | None
    patient_history: list[dict[str, Any]]
    returning_patient: bool | None

    # Current structured clinical data
    encounter: dict[str, Any] | None
    symptoms: list[dict[str, Any]]
    vitals: list[dict[str, Any]]
    labs: list[dict[str, Any]]

    # Multimodal inputs
    raw_text: str | None
    transcript: str | None
    ocr_text: str | None
    image_results: list[dict[str, Any]]
    document_results: list[dict[str, Any]]
    speech_results: list[dict[str, Any]]
    wearable_data: list[dict[str, Any]]

    # Normalized and fused data
    normalized_symptoms: list[dict[str, Any]]
    current_vitals: dict[str, Any] | None
    previous_vitals: list[dict[str, Any]]
    current_labs: dict[str, dict[str, Any]]
    fused_context: dict[str, Any] | None

    # Assessment outputs
    cardiac_risk: dict[str, Any] | None
    triage: dict[str, Any] | None
    clinical_reasoning: dict[str, Any] | None
    safety_findings: dict[str, Any] | None
    explanation: dict[str, Any] | None
    priority: dict[str, Any] | None

    # Orchestration state
    next_action: str | None
    completed_agents: list[str]
    workflow_status: str
    missing_information: list[str]
    warnings: list[str]
    errors: list[str]
    agent_trace: list[AgentTraceEntry]
    capability_status: dict[str, CapabilityStatus]
    workflow_halted: bool


def create_initial_clinical_state(patient_id: str, encounter_id: str) -> ClinicalState:
    """Create a complete, JSON-safe state without fabricating unavailable values."""

    return ClinicalState(
        workflow_id=str(uuid4()),
        patient_id=patient_id,
        encounter_id=encounter_id,
        patient=None,
        patient_history=[],
        returning_patient=None,
        encounter=None,
        symptoms=[],
        vitals=[],
        labs=[],
        raw_text=None,
        transcript=None,
        ocr_text=None,
        image_results=[],
        document_results=[],
        speech_results=[],
        wearable_data=[],
        normalized_symptoms=[],
        current_vitals=None,
        previous_vitals=[],
        current_labs={},
        fused_context=None,
        cardiac_risk=None,
        triage=None,
        clinical_reasoning=None,
        safety_findings=None,
        explanation=None,
        priority=None,
        next_action=None,
        completed_agents=[],
        workflow_status="INITIALIZED",
        missing_information=[],
        warnings=[],
        errors=[],
        agent_trace=[],
        capability_status={},
        workflow_halted=False,
    )

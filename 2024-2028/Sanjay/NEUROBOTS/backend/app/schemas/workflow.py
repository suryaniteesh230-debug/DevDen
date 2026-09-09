from typing import Any

from pydantic import BaseModel, ConfigDict


class ClinicalWorkflowResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    workflow_id: str
    patient_id: str
    encounter_id: str
    patient: dict[str, Any] | None
    patient_history: list[dict[str, Any]]
    returning_patient: bool | None
    encounter: dict[str, Any] | None
    symptoms: list[dict[str, Any]]
    vitals: list[dict[str, Any]]
    labs: list[dict[str, Any]]
    raw_text: str | None
    transcript: str | None
    ocr_text: str | None
    image_results: list[dict[str, Any]]
    document_results: list[dict[str, Any]]
    speech_results: list[dict[str, Any]]
    wearable_data: list[dict[str, Any]]
    normalized_symptoms: list[dict[str, Any]]
    current_vitals: dict[str, Any] | None
    previous_vitals: list[dict[str, Any]]
    current_labs: dict[str, dict[str, Any]]
    fused_context: dict[str, Any] | None
    cardiac_risk: dict[str, Any] | None
    triage: dict[str, Any] | None
    clinical_reasoning: dict[str, Any] | None
    safety_findings: dict[str, Any] | None
    explanation: dict[str, Any] | None
    priority: dict[str, Any] | None
    next_action: str | None
    completed_agents: list[str]
    workflow_status: str
    missing_information: list[str]
    warnings: list[str]
    errors: list[str]
    agent_trace: list[dict[str, Any]]
    capability_status: dict[str, dict[str, Any]]
    workflow_halted: bool

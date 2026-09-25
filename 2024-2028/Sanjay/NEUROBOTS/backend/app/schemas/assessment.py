from typing import Any

from pydantic import BaseModel, ConfigDict


class LatestAssessmentRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient: dict[str, Any]
    encounter: dict[str, Any]
    cardiac_risk: dict[str, Any] | None
    triage: dict[str, Any] | None
    explanation: dict[str, Any] | None
    clinical_reasoning: dict[str, Any] | None
    priority: dict[str, Any] | None
    documents: list[dict[str, Any]]
    speech: list[dict[str, Any]]


class AssessmentHistoryRead(LatestAssessmentRead):
    risk_predictions: list[dict[str, Any]]
    triage_assessments: list[dict[str, Any]]
    explanations: list[dict[str, Any]]
    clinical_reasoning_results: list[dict[str, Any]]
    priority_calculations: list[dict[str, Any]]

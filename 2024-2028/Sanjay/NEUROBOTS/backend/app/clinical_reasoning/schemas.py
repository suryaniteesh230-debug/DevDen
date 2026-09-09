from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


REASONING_SCHEMA_VERSION = "clinical-reasoning-output-1.0.0"


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SupportLevel(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


class DifferentialConsideration(StrictSchema):
    condition: str = Field(min_length=1, max_length=160)
    support_level: SupportLevel
    supporting_findings: list[str] = Field(max_length=12)
    contradicting_or_missing_findings: list[str] = Field(max_length=12)
    evidence_refs: list[str] = Field(max_length=16)


class SymptomCorrelation(StrictSchema):
    symptoms: list[str] = Field(min_length=1, max_length=8)
    associated_with: str = Field(min_length=1, max_length=240)
    evidence_refs: list[str] = Field(max_length=12)
    relationship_type: Literal["ASSOCIATION"]


class ClinicalEvidence(StrictSchema):
    source_id: str = Field(min_length=1, max_length=120)
    chunk_id: str = Field(min_length=1, max_length=160)
    relevance: float = Field(ge=0, le=1)


class KnowledgeGraphEvidence(StrictSchema):
    edge_id: str = Field(min_length=1, max_length=160)
    source_concept: str = Field(min_length=1, max_length=160)
    relationship: str = Field(min_length=1, max_length=120)
    target_concept: str = Field(min_length=1, max_length=160)
    source_id: str = Field(min_length=1, max_length=120)
    relevance: float = Field(ge=0, le=1)


class ClinicalConsideration(StrictSchema):
    consideration: str = Field(min_length=1, max_length=500)
    evidence_refs: list[str] = Field(min_length=1, max_length=12)


class ReasoningToolTrace(StrictSchema):
    step: int = Field(ge=1)
    tool: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=240)
    status: str = Field(min_length=1, max_length=40)
    result_references: list[str] = Field(max_length=24)
    latency_ms: float = Field(ge=0)


class ClinicalReasoningOutput(StrictSchema):
    summary: str = Field(min_length=1, max_length=2000)
    differential_considerations: list[DifferentialConsideration] = Field(max_length=12)
    symptom_correlations: list[SymptomCorrelation] = Field(max_length=16)
    clinical_evidence: list[ClinicalEvidence] = Field(max_length=24)
    knowledge_graph_evidence: list[KnowledgeGraphEvidence] = Field(max_length=24)
    important_missing_information: list[str] = Field(max_length=24)
    clinical_considerations: list[ClinicalConsideration] = Field(max_length=16)
    uncertainty: str = Field(min_length=1, max_length=1000)
    tool_calls: list[ReasoningToolTrace] = Field(max_length=12)
    limitations: list[str] = Field(min_length=1, max_length=16)

    @field_validator("summary", "uncertainty")
    @classmethod
    def reject_numeric_disease_probabilities(cls, value: str) -> str:
        pattern = re.compile(
            r"\b(probability|likelihood|chance)\b[^.\n]{0,30}\b\d+(?:\.\d+)?\s*%?",
            re.IGNORECASE,
        )
        if pattern.search(value):
            raise ValueError("unsupported numeric disease probability is not allowed")
        return value

    @model_validator(mode="after")
    def reject_probability_fields_in_nested_data(self) -> "ClinicalReasoningOutput":
        # `extra=forbid` rejects explicit probability/confidence fields. This check
        # covers numeric probability wording in the remaining narrative fields.
        narratives: list[str] = []
        for item in self.differential_considerations:
            narratives.extend(item.supporting_findings)
            narratives.extend(item.contradicting_or_missing_findings)
        narratives.extend(item.consideration for item in self.clinical_considerations)
        numeric_claim = re.compile(
            r"\b(probability|likelihood|chance)\b[^.\n]{0,30}\b\d+(?:\.\d+)?\s*%?",
            re.IGNORECASE,
        )
        if any(numeric_claim.search(text) for text in narratives):
            raise ValueError("unsupported numeric disease probability is not allowed")
        return self


def collect_output_evidence_refs(output: ClinicalReasoningOutput) -> set[str]:
    refs: set[str] = set()
    for item in output.differential_considerations:
        refs.update(item.evidence_refs)
    for item in output.symptom_correlations:
        refs.update(item.evidence_refs)
    for item in output.clinical_considerations:
        refs.update(item.evidence_refs)
    refs.update(item.chunk_id for item in output.clinical_evidence)
    refs.update(item.edge_id for item in output.knowledge_graph_evidence)
    return refs


def json_schema_for_prompt() -> dict[str, Any]:
    return ClinicalReasoningOutput.model_json_schema()

from __future__ import annotations

import re
from time import perf_counter
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.clinical_reasoning.knowledge_graph import MedicalKnowledgeGraph
from app.clinical_reasoning.retrieval import ClinicalKnowledgeRetriever
from app.core.config import get_settings
from app.repositories.clinical import EncounterRepository, ObservationRepository


APPROVED_REASONING_TOOLS = (
    "get_patient_history",
    "get_current_vitals",
    "get_current_labs",
    "retrieve_clinical_guidelines",
    "query_medical_knowledge_graph",
)
RELEVANT_CARDIAC_LAB_KEYS = {
    "troponin",
    "troponini",
    "troponint",
    "highsensitivitytroponin",
    "hstn",
    "ckmb",
    "creatinekinasemb",
    "bloodsugar",
    "glucose",
}


def _is_relevant_lab(test_name: str) -> bool:
    return re.sub(r"[^a-z0-9]+", "", test_name.casefold()) in RELEVANT_CARDIAC_LAB_KEYS


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    purpose: str = Field(min_length=1, max_length=240)


class HistoryInput(ToolInput):
    max_encounters: int = Field(default=3, ge=1, le=5)


class CurrentContextInput(ToolInput):
    pass


class RetrievalInput(ToolInput):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=3, ge=1, le=5)


class KnowledgeGraphInput(ToolInput):
    query: str = Field(min_length=1, max_length=300)
    max_results: int = Field(default=5, ge=1, le=8)


class ReasoningToolError(RuntimeError):
    pass


class ClinicalReasoningToolRegistry:
    """Exact allow-list for the clinical reasoning agent.

    Patient and encounter identifiers are bound locally at construction and are
    never accepted as LLM-controlled arguments.
    """

    def __init__(
        self,
        session: Session,
        *,
        patient_id: str,
        encounter_id: str,
        retriever: ClinicalKnowledgeRetriever | None = None,
        knowledge_graph: MedicalKnowledgeGraph | None = None,
    ) -> None:
        settings = get_settings()
        self.patient_id = patient_id
        self.encounter_id = encounter_id
        self.encounters = EncounterRepository(session)
        self.observations = ObservationRepository(session)
        self.retriever = retriever or ClinicalKnowledgeRetriever(
            settings.clinical_corpus_path, settings.clinical_vector_index_path
        )
        self.knowledge_graph = knowledge_graph or MedicalKnowledgeGraph(
            settings.medical_knowledge_graph_path
        )
        self._schemas: dict[str, type[ToolInput]] = {
            "get_patient_history": HistoryInput,
            "get_current_vitals": CurrentContextInput,
            "get_current_labs": CurrentContextInput,
            "retrieve_clinical_guidelines": RetrievalInput,
            "query_medical_knowledge_graph": KnowledgeGraphInput,
        }
        self._handlers: dict[str, Callable[[ToolInput], dict[str, Any]]] = {
            "get_patient_history": self._history,
            "get_current_vitals": self._vitals,
            "get_current_labs": self._labs,
            "retrieve_clinical_guidelines": self._retrieve,
            "query_medical_knowledge_graph": self._query_graph,
        }

    @property
    def names(self) -> tuple[str, ...]:
        return APPROVED_REASONING_TOOLS

    def definitions(self) -> list[dict[str, Any]]:
        descriptions = {
            "get_patient_history": "Get clinically relevant prior encounters and findings; use only when history could change the current reasoning.",
            "get_current_vitals": "Get the latest current-encounter vital signs with timestamp and source provenance.",
            "get_current_labs": "Get current-encounter laboratory observations with timestamps and source provenance.",
            "retrieve_clinical_guidelines": "Search the small local ACS/chest-pain corpus. Use a focused clinical query; results always include provenance.",
            "query_medical_knowledge_graph": "Query source-backed ACS symptom, finding, evaluation, and condition relationships. This is constrained graph lookup, not arbitrary graph execution.",
        }
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": descriptions[name],
                    "parameters": self._schemas[name].model_json_schema(),
                },
            }
            for name in APPROVED_REASONING_TOOLS
        ]

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self._handlers:
            raise ReasoningToolError(f"Tool '{name}' is not approved")
        timer = perf_counter()
        try:
            validated = self._schemas[name].model_validate(arguments)
            result = self._handlers[name](validated)
        except ValidationError as exception:
            raise ReasoningToolError(f"Invalid arguments for approved tool '{name}'") from exception
        result["tool_latency_ms"] = round((perf_counter() - timer) * 1000, 3)
        return result

    def _history(self, inputs: ToolInput) -> dict[str, Any]:
        assert isinstance(inputs, HistoryInput)
        history = [
            encounter
            for encounter in self.encounters.history_for_patient(self.patient_id)
            if encounter.id != self.encounter_id
        ][: inputs.max_encounters]
        results: list[dict[str, Any]] = []
        for index, encounter in enumerate(history, start=1):
            results.append(
                {
                    "history_reference": f"HISTORY-{index}",
                    "encounter_type": encounter.encounter_type,
                    "status": encounter.status.value,
                    "started_at": encounter.started_at.isoformat(),
                    "symptoms": [
                        {
                            "name": symptom.name,
                            "severity": symptom.severity,
                            "duration": symptom.duration,
                            "present": symptom.present,
                            "source": symptom.source.value,
                        }
                        for symptom in encounter.symptoms
                    ],
                    "latest_vitals": (
                        self._serialize_vitals(encounter.vital_signs[-1])
                        if encounter.vital_signs
                        else None
                    ),
                    "labs": [
                        self._serialize_lab(lab)
                        for lab in encounter.lab_results[-12:]
                        if _is_relevant_lab(lab.test_name)
                    ],
                }
            )
        return {"status": "SUCCESS", "results": results}

    def _vitals(self, _inputs: ToolInput) -> dict[str, Any]:
        vitals = self.observations.list_vitals(self.encounter_id)
        latest = self._serialize_vitals(vitals[-1]) if vitals else None
        return {
            "status": "SUCCESS" if latest else "NO_DATA",
            "result": latest,
            "result_reference": "CURRENT-VITALS" if latest else None,
        }

    def _labs(self, _inputs: ToolInput) -> dict[str, Any]:
        labs = [
            lab
            for lab in self.observations.list_labs(self.encounter_id)
            if _is_relevant_lab(lab.test_name)
        ]
        results = [self._serialize_lab(lab) for lab in labs[-20:]]
        return {
            "status": "SUCCESS" if results else "NO_DATA",
            "results": results,
            "result_references": [f"CURRENT-LAB-{index}" for index in range(1, len(results) + 1)],
        }

    def _retrieve(self, inputs: ToolInput) -> dict[str, Any]:
        assert isinstance(inputs, RetrievalInput)
        return self.retriever.retrieve(inputs.query, top_k=inputs.top_k)

    def _query_graph(self, inputs: ToolInput) -> dict[str, Any]:
        assert isinstance(inputs, KnowledgeGraphInput)
        return self.knowledge_graph.query(inputs.query, max_results=inputs.max_results)

    @staticmethod
    def _serialize_vitals(vitals: Any) -> dict[str, Any]:
        return {
            "heart_rate": vitals.heart_rate,
            "systolic_bp": vitals.systolic_bp,
            "diastolic_bp": vitals.diastolic_bp,
            "spo2": vitals.spo2,
            "respiratory_rate": vitals.respiratory_rate,
            "temperature": vitals.temperature,
            "measured_at": vitals.measured_at.isoformat(),
            "source": vitals.source.value,
        }

    @staticmethod
    def _serialize_lab(lab: Any) -> dict[str, Any]:
        return {
            "test_name": lab.test_name,
            "value": lab.value,
            "unit": lab.unit,
            "collected_at": lab.collected_at.isoformat(),
            "source": lab.source.value,
            "reference_metadata": lab.reference_metadata,
        }


def result_references(result: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    if result.get("result_reference"):
        refs.append(str(result["result_reference"]))
    refs.extend(str(ref) for ref in result.get("result_references", []))
    for item in result.get("results", []):
        for key in ("chunk_id", "edge_id", "history_reference", "source_id"):
            if item.get(key):
                refs.append(str(item[key]))
        provenance = item.get("provenance") or {}
        if provenance.get("source_id"):
            refs.append(str(provenance["source_id"]))
    return list(dict.fromkeys(refs))

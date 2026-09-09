"""Benchmark the complete agent locally with deterministic scripted Gemini turns.

This intentionally does not claim cloud latency. It includes the bounded loop,
local RAG, local KG, validation, and SQLite persistence.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from statistics import mean, median
from typing import Any

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agents.clinical_reasoning_agent import ClinicalReasoningAgent
from app.clinical_reasoning.schemas import ClinicalReasoningOutput
from app.db.base import Base
from app.db.models import ClinicalEncounter, Patient
from app.llm.base import LLMProvider, ProviderTurn, ToolCallRequest
from app.workflows.clinical_state import create_initial_clinical_state


RUNS = 200
OUTPUT_PATH = Path(__file__).with_name("latency_benchmark.json")


class ScriptedLocalProvider(LLMProvider):
    provider_name = "Gemini-mock"
    model = "gemini-3.6-flash"
    available = True

    def generate_with_tools(self, *, messages: list[dict[str, Any]], **_kwargs) -> ProviderTurn:
        tool_results = sum(message.get("role") == "tool" for message in messages)
        if tool_results == 0:
            call = ToolCallRequest(
                id="kg",
                name="query_medical_knowledge_graph",
                arguments={
                    "purpose": "Correlate current symptoms with source-backed concepts",
                    "query": "chest pain dyspnea troponin acute coronary syndrome",
                    "max_results": 5,
                },
            )
        elif tool_results == 1:
            call = ToolCallRequest(
                id="rag",
                name="retrieve_clinical_guidelines",
                arguments={
                    "purpose": "Retrieve acute chest-pain evaluation evidence",
                    "query": "acute chest pain ECG serial troponin evaluation",
                    "top_k": 3,
                },
            )
        else:
            return ProviderTurn(
                provider=self.provider_name,
                model=self.model,
                assistant_message={"role": "assistant", "content": "Evidence is sufficient."},
                latency_ms=0,
            )
        return ProviderTurn(
            provider=self.provider_name,
            model=self.model,
            assistant_message={
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                ],
            },
            tool_calls=[call],
            latency_ms=0,
        )

    def generate_structured(self, **_kwargs) -> ProviderTurn:
        output = ClinicalReasoningOutput.model_validate(
                {
                    "summary": "Findings support urgent clinician assessment for possible ACS.",
                    "differential_considerations": [
                        {
                            "condition": "Acute coronary syndrome",
                            "support_level": "HIGH",
                            "supporting_findings": ["Chest pain and dyspnea"],
                            "contradicting_or_missing_findings": ["ECG unavailable"],
                            "evidence_refs": ["KG-ACS-001", "CHEST21-ECG-01"],
                        }
                    ],
                    "symptom_correlations": [],
                    "clinical_evidence": [],
                    "knowledge_graph_evidence": [],
                    "important_missing_information": ["12-lead ECG"],
                    "clinical_considerations": [
                        {
                            "consideration": "Prompt clinician-led emergency evaluation.",
                            "evidence_refs": ["CHEST21-ECG-01"],
                        }
                    ],
                    "uncertainty": "This narrow corpus cannot confirm a diagnosis.",
                    "tool_calls": [],
                    "limitations": ["Not a diagnosis or treatment order"],
                }
            )
        return ProviderTurn(
            provider=self.provider_name,
            model=self.model,
            assistant_message={"role": "assistant", "content": output.model_dump_json()},
            structured_output=output,
            latency_ms=0,
        )


def main() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        patient = Patient(
            external_patient_id="BENCH-001",
            first_name="Benchmark",
            last_name="Patient",
            date_of_birth=date(1970, 1, 1),
            gender="unspecified",
        )
        encounter = ClinicalEncounter(
            patient=patient,
            encounter_type="emergency",
            chief_complaint="Chest pain",
        )
        session.add(encounter)
        session.commit()
        latencies: list[float] = []
        for _ in range(RUNS):
            state = create_initial_clinical_state(patient.id, encounter.id)
            state["normalized_symptoms"] = [
                {"name": "chest pain"},
                {"name": "shortness of breath"},
            ]
            result = ClinicalReasoningAgent(
                session, provider=ScriptedLocalProvider()
            )(state)["clinical_reasoning"]
            latencies.append(result["latency_ms"])
    existing = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    existing["clinical_reasoning_agent_mocked_provider"] = {
        "scope": "Complete agent with zero-latency scripted provider; includes local RAG, KG, validation, and SQLite persistence; excludes Gemini network latency",
        "runs": RUNS,
        "mean_ms": round(mean(latencies), 4),
        "p50_ms": round(median(latencies), 4),
        "p95_ms": round(float(np.percentile(latencies, 95)), 4),
    }
    OUTPUT_PATH.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(existing["clinical_reasoning_agent_mocked_provider"], indent=2))


if __name__ == "__main__":
    main()

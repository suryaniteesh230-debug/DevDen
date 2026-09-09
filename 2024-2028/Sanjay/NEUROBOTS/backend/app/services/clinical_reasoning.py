from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import ClinicalReasoningResult
from app.repositories.clinical import ClinicalReasoningResultRepository


class ClinicalReasoningPersistenceService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.results = ClinicalReasoningResultRepository(session)

    def persist(
        self,
        *,
        encounter_id: str,
        workflow_id: str,
        agent_name: str,
        agent_version: str,
        provider: str,
        model: str,
        schema_version: str,
        summary: str,
        structured_output: dict[str, Any],
        retrieved_source_ids: list[str],
        knowledge_graph_evidence: list[dict[str, Any]],
        tool_call_trace: list[dict[str, Any]],
        termination_reason: str,
        latency_ms: float,
    ) -> ClinicalReasoningResult:
        row = self.results.add(
            ClinicalReasoningResult(
                encounter_id=encounter_id,
                workflow_id=workflow_id,
                agent_name=agent_name,
                agent_version=agent_version,
                provider=provider,
                model=model,
                schema_version=schema_version,
                summary=summary,
                structured_output=structured_output,
                retrieved_source_ids=list(dict.fromkeys(retrieved_source_ids)),
                knowledge_graph_evidence=knowledge_graph_evidence,
                tool_call_trace=tool_call_trace,
                termination_reason=termination_reason,
                latency_ms=latency_ms,
            )
        )
        self.session.commit()
        self.session.refresh(row)
        return row

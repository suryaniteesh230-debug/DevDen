from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import TriageAssessment
from app.repositories.clinical import TriageAssessmentRepository


class TriageAssessmentPersistenceService:
    """Append a new immutable triage assessment for every policy evaluation."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.assessments = TriageAssessmentRepository(session)

    def persist(
        self, encounter_id: str, result: dict[str, Any]
    ) -> TriageAssessment:
        assessment = self.assessments.add(
            TriageAssessment(
                encounter_id=encounter_id,
                policy_name=result["policy_name"],
                policy_version=result["policy_version"],
                severity_level=result["severity_level"],
                provisional=result["provisional"],
                completeness_metadata=result["completeness"],
                confidence_metadata=result["confidence"],
                rule_hits=result["rule_hits"],
                missing_information=result["missing_information"],
                input_snapshot=result["input_snapshot"],
                evaluation_latency_ms=result["evaluation_latency_ms"],
            )
        )
        self.session.commit()
        self.session.refresh(assessment)
        return assessment

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Explanation, QueuePriorityCalculation
from app.repositories.clinical import (
    ClinicalDocumentRepository,
    ClinicalReasoningResultRepository,
    ExplanationRepository,
    QueueEntryRepository,
    RiskPredictionRepository,
    SpeechTranscriptionRepository,
    TriageAssessmentRepository,
)
from app.schemas.clinical import EncounterDetail, PatientRead
from app.schemas.multimodal import ClinicalDocumentRead
from app.schemas.queue import queue_entry_payload
from app.schemas.speech import SpeechTranscriptionRead
from app.services.encounters import EncounterService
from app.services.dynamic_queue import DynamicQueueService
from app.services.patients import PatientService


class AssessmentHistoryService:
    """Read-only persisted assessment projection for frontend consumption."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.risks = RiskPredictionRepository(session)
        self.triage = TriageAssessmentRepository(session)
        self.reasoning = ClinicalReasoningResultRepository(session)
        self.queue = QueueEntryRepository(session)
        self.documents = ClinicalDocumentRepository(session)
        self.speech = SpeechTranscriptionRepository(session)

    def latest(self, encounter_id: str) -> dict[str, Any]:
        context = self._context(encounter_id)
        risks = self.risks.list_for_encounter(encounter_id)
        triage = self.triage.list_for_encounter(encounter_id)
        reasoning = self.reasoning.list_for_encounter(encounter_id)
        latest_risk = risks[-1] if risks else None
        latest_explanation = self._latest_explanation(latest_risk.id) if latest_risk else None
        queue_entry = self.queue.get_for_encounter(encounter_id)
        return {
            **context,
            "cardiac_risk": self._risk(latest_risk) if latest_risk else None,
            "triage": self._triage(triage[-1]) if triage else None,
            "explanation": self._explanation(latest_explanation) if latest_explanation else None,
            "clinical_reasoning": self._reasoning(reasoning[-1]) if reasoning else None,
            "priority": (
                queue_entry_payload(
                    queue_entry,
                    rank=DynamicQueueService(self.session).rank(queue_entry.id),
                    include_trace=True,
                )
                if queue_entry
                else None
            ),
            "documents": [
                ClinicalDocumentRead.model_validate(item).model_dump(mode="json")
                for item in self.documents.list_for_encounter(encounter_id)
            ],
            "speech": [
                SpeechTranscriptionRead.model_validate(item).model_dump(mode="json")
                for item in self.speech.list_for_encounter(encounter_id)
            ],
        }

    def history(self, encounter_id: str) -> dict[str, Any]:
        latest = self.latest(encounter_id)
        risks = self.risks.list_for_encounter(encounter_id)
        triage = self.triage.list_for_encounter(encounter_id)
        reasoning = self.reasoning.list_for_encounter(encounter_id)
        explanations = list(
            self.session.scalars(
                select(Explanation)
                .join(Explanation.prediction)
                .where(Explanation.prediction.has(encounter_id=encounter_id))
                .order_by(Explanation.generated_at, Explanation.id)
            ).all()
        )
        queue_entry = self.queue.get_for_encounter(encounter_id)
        calculations = (
            list(
                self.session.scalars(
                    select(QueuePriorityCalculation)
                    .where(QueuePriorityCalculation.queue_entry_id == queue_entry.id)
                    .order_by(
                        QueuePriorityCalculation.calculated_at,
                        QueuePriorityCalculation.id,
                    )
                ).all()
            )
            if queue_entry
            else []
        )
        return {
            **latest,
            "risk_predictions": [self._risk(item) for item in risks],
            "triage_assessments": [self._triage(item) for item in triage],
            "explanations": [self._explanation(item) for item in explanations],
            "clinical_reasoning_results": [self._reasoning(item) for item in reasoning],
            "priority_calculations": [self._calculation(item) for item in calculations],
        }

    def _context(self, encounter_id: str) -> dict[str, Any]:
        encounter = EncounterService(self.session).get(encounter_id)
        patient = PatientService(self.session).get(encounter.patient_id)
        return {
            "patient": PatientRead.model_validate(patient).model_dump(mode="json"),
            "encounter": EncounterDetail.model_validate(encounter).model_dump(mode="json"),
        }

    def _latest_explanation(self, prediction_id: str) -> Explanation | None:
        items = ExplanationRepository(self.session).list_for_prediction(prediction_id)
        return items[-1] if items else None

    @staticmethod
    def _risk(item: Any) -> dict[str, Any]:
        return {
            "status": "SUCCESS",
            "prediction_id": item.id,
            "model_name": item.model_name,
            "model_version": item.model_version,
            "predicted_class": item.predicted_class,
            "probability": item.probability,
            "threshold": item.threshold,
            "input_features": item.input_feature_snapshot,
            "inference_latency_ms": item.inference_latency_ms,
            "created_at": item.created_at.isoformat(),
        }

    @staticmethod
    def _triage(item: Any) -> dict[str, Any]:
        return {
            "status": "SUCCESS",
            "assessment_id": item.id,
            "policy_name": item.policy_name,
            "policy_version": item.policy_version,
            "severity_level": item.severity_level,
            "prototype_esi_level": 2 if item.severity_level == "PROTOTYPE_ESI_2" else None,
            "provisional": item.provisional,
            "completeness": item.completeness_metadata,
            "confidence": item.confidence_metadata,
            "rule_hits": item.rule_hits,
            "triggered_rule_ids": [
                rule.get("rule_id") for rule in item.rule_hits if rule.get("triggered")
            ],
            "missing_information": item.missing_information,
            "input_snapshot": item.input_snapshot,
            "evaluation_latency_ms": item.evaluation_latency_ms,
            "created_at": item.created_at.isoformat(),
        }

    @staticmethod
    def _explanation(item: Any) -> dict[str, Any]:
        return {
            "status": "SUCCESS",
            "explanation_id": item.id,
            "prediction_id": item.prediction_id,
            "method": item.explanation_method,
            "explainer_version": item.explainer_version,
            "model_version": item.model_version,
            "feature_contributions": item.feature_contributions,
            "counterfactual": item.counterfactual,
            "clinical_evidence": item.clinical_evidence,
            "imaging_saliency": item.saliency,
            "generated_at": item.generated_at.isoformat(),
        }

    @staticmethod
    def _reasoning(item: Any) -> dict[str, Any]:
        status = (
            "SUCCESS"
            if item.structured_output
            else (
                "PENDING_CAPABILITY"
                if item.termination_reason == "PROVIDER_UNAVAILABLE"
                else "PARTIAL"
            )
        )
        provider = str(getattr(item, "provider", "")).strip() or "gemini"
        model = str(getattr(item, "model", "")).strip()
        summary = str(getattr(item, "summary", "")).strip()
        termination_reason = str(getattr(item, "termination_reason", "")).strip()
        legacy_groq_record = provider.casefold() == "groq" or "groq" in summary.casefold()
        if legacy_groq_record:
            provider = "gemini"
            if termination_reason == "PROVIDER_RATE_LIMITED":
                summary = "Clinical reasoning rate limit reached"
            elif termination_reason == "PROVIDER_FAILURE" and "groq" in summary.casefold():
                summary = "Clinical reasoning provider failed"
        return {
            "status": status,
            "result_id": item.id,
            "workflow_id": item.workflow_id,
            "agent_name": item.agent_name,
            "agent_version": item.agent_version,
            "provider": provider,
            "model": model,
            "schema_version": item.schema_version,
            "summary": summary,
            "retrieved_source_ids": item.retrieved_source_ids,
            "knowledge_graph_evidence": item.knowledge_graph_evidence,
            "tool_calls": item.tool_call_trace,
            "termination_reason": termination_reason,
            "latency_ms": item.latency_ms,
            "created_at": item.created_at.isoformat(),
            **item.structured_output,
        }

    @staticmethod
    def _calculation(item: Any) -> dict[str, Any]:
        return {
            "calculation_id": item.id,
            "queue_entry_id": item.queue_entry_id,
            "triage_assessment_id": item.triage_assessment_id,
            "risk_prediction_id": item.risk_prediction_id,
            "policy_name": item.policy_name,
            "policy_version": item.policy_version,
            "priority_score": item.priority_score,
            "priority_band": item.priority_band.value,
            "reason_codes": item.reason_codes,
            "rule_trace": item.rule_trace,
            "input_snapshot": item.input_snapshot,
            "deterioration_status": item.deterioration_status,
            "calculated_at": item.calculated_at.isoformat(),
        }

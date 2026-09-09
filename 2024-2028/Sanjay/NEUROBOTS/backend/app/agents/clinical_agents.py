from __future__ import annotations

import re
from collections import Counter
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agents.contracts import (
    AgentExecutionStatus,
    AgentOutput,
    CapabilityAvailability,
    ClinicalAgent,
    capability,
)
from app.agents.clinical_reasoning_agent import ClinicalReasoningAgent
from app.clinical_reasoning.schemas import ClinicalReasoningOutput, collect_output_evidence_refs
from app.ml.cardiac_risk import CardiacRiskTool
from app.ml.explanation import ShapExplanationTool
from app.ml.features import build_cardiac_features
from app.priority.policy import DynamicPriorityPolicy
from app.repositories.clinical import ClinicalDocumentRepository, SpeechTranscriptionRepository
from app.schemas.clinical import EncounterDetail, PatientRead
from app.services.encounters import EncounterService
from app.services.dynamic_queue import DynamicQueueService
from app.services.patients import PatientService
from app.services.risk_assessment import RiskAssessmentPersistenceService
from app.services.triage import TriageAssessmentPersistenceService
from app.triage.policy import EmergencyTriageTool
from app.workflows.clinical_state import ClinicalState


def _serialize(model: Any, schema: type) -> dict[str, Any]:
    return schema.model_validate(model).model_dump(mode="json")


def _normal_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _lab_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _sources(items: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(item.get("source", "UNKNOWN")) for item in items))


class IntakeAgent(ClinicalAgent):
    name = "intake"
    critical = True

    def __init__(self, session: Session) -> None:
        self.patients = PatientService(session)
        self.encounters = EncounterService(session)

    def run(self, state: ClinicalState) -> AgentOutput:
        patient_id = state.get("patient_id")
        encounter_id = state.get("encounter_id")
        if not patient_id or not encounter_id:
            missing = [
                name
                for name, value in (("patient_id", patient_id), ("encounter_id", encounter_id))
                if not value
            ]
            raise ValueError(f"Missing required workflow identifiers: {', '.join(missing)}")

        self.patients.get(patient_id)
        encounter = self.encounters.get(encounter_id)
        if encounter.patient_id != patient_id:
            raise ValueError(
                f"Encounter '{encounter_id}' does not belong to patient '{patient_id}'"
            )

        encounter_data = _serialize(encounter, EncounterDetail)
        missing_information = list(state.get("missing_information", []))
        category_counts = {
            "symptoms": len(encounter_data["symptoms"]),
            "vitals": len(encounter_data["vital_signs"]),
            "labs": len(encounter_data["lab_results"]),
        }
        for category, count in category_counts.items():
            if count == 0:
                missing_information.append(f"current_{category}")

        status = (
            AgentExecutionStatus.PARTIAL
            if any(count == 0 for count in category_counts.values())
            else AgentExecutionStatus.SUCCESS
        )
        return AgentOutput(
            status=status,
            summary="Verified workflow identifiers and loaded the current encounter",
            updates={
                "encounter": {
                    key: value
                    for key, value in encounter_data.items()
                    if key not in {"symptoms", "vital_signs", "lab_results"}
                },
                "symptoms": encounter_data["symptoms"],
                "vitals": encounter_data["vital_signs"],
                "labs": encounter_data["lab_results"],
                "missing_information": list(dict.fromkeys(missing_information)),
                "workflow_halted": False,
                "workflow_status": "RUNNING",
            },
        )


class MultimodalAgent(ClinicalAgent):
    name = "multimodal"

    def __init__(self, session: Session) -> None:
        self.documents = ClinicalDocumentRepository(session)
        self.transcriptions = SpeechTranscriptionRepository(session)

    def run(self, state: ClinicalState) -> AgentOutput:
        observations = [*state.get("symptoms", []), *state.get("vitals", []), *state.get("labs", [])]
        source_counts = _sources(observations) if observations else {}
        documents = self.documents.list_for_encounter(state["encounter_id"])
        transcriptions = self.transcriptions.list_for_encounter(state["encounter_id"])
        document_results = [
            {
                "document_id": item.id,
                "filename": item.safe_filename,
                "status": item.processing_status,
                "source": item.source.value,
                "ocr_engine": item.ocr_engine,
                "ocr_engine_version": item.ocr_engine_version,
                "ocr_confidence": item.ocr_confidence,
                "extracted_fields": item.extracted_fields,
                "conflicts": item.conflicts,
                "lab_result_ids": item.lab_result_ids,
                "processed_at": item.processed_at.isoformat(),
            }
            for item in documents
        ]
        ocr_text = "\n\n".join(item.ocr_text for item in documents if item.ocr_text) or None
        speech_results = [
            {
                "transcription_id": item.id,
                "filename": item.safe_filename,
                "status": item.processing_status,
                "source": item.source.value,
                "provider": item.provider,
                "model": item.model,
                "language": item.language,
                "confidence_metadata": item.confidence_metadata,
                "extracted_symptoms": item.extracted_symptoms,
                "conflicts": item.conflicts,
                "symptom_ids": item.symptom_ids,
                "processed_at": item.processed_at.isoformat(),
            }
            for item in transcriptions
        ]
        transcript = "\n\n".join(item.transcript for item in transcriptions if item.transcript) or None
        capabilities = {
            "structured_observation_ingestion": capability(
                CapabilityAvailability.AVAILABLE,
                "Structured encounter observations are available",
                source_counts=source_counts,
            ),
            "speech_transcription": capability(
                (
                    CapabilityAvailability.AVAILABLE
                    if transcriptions
                    else CapabilityAvailability.PARTIAL
                ),
                (
                    "Persisted English speech transcripts are available"
                    if transcriptions
                    else "Gemini speech ingestion is implemented; no transcript was supplied"
                ),
                transcription_count=len(transcriptions),
            ),
            "ocr_extraction": capability(
                CapabilityAvailability.AVAILABLE,
                "Persisted documents are processed by the local Tesseract adapter",
                document_count=len(documents),
            ),
            "medical_image_interpretation": capability(
                CapabilityAvailability.PENDING_CAPABILITY,
                "No medical-image interpretation model is available",
            ),
            "wearable_telemetry": capability(
                CapabilityAvailability.PENDING_CAPABILITY,
                "Wearable provenance is supported, but a telemetry adapter is not implemented",
            ),
        }
        return AgentOutput(
            status=AgentExecutionStatus.PARTIAL,
            summary=(
                f"Recognized {len(observations)} structured observations and "
                f"{len(documents)} locally processed documents and "
                f"{len(transcriptions)} speech transcripts"
            ),
            updates={
                "document_results": document_results,
                "ocr_text": ocr_text,
                "speech_results": speech_results,
                "transcript": transcript,
            },
            capabilities=capabilities,
        )


class PatientResolutionAgent(ClinicalAgent):
    name = "patient_resolution"

    def __init__(self, session: Session) -> None:
        self.patients = PatientService(session)

    def run(self, state: ClinicalState) -> AgentOutput:
        patient, history = self.patients.history(state["patient_id"])
        prior_encounters = [
            _serialize(encounter, EncounterDetail)
            for encounter in history
            if encounter.id != state["encounter_id"]
        ]
        returning = bool(prior_encounters)
        return AgentOutput(
            status=AgentExecutionStatus.SUCCESS,
            summary=(
                f"Resolved returning patient with {len(prior_encounters)} prior encounters"
                if returning
                else "Resolved patient with no prior encounters"
            ),
            updates={
                "patient": _serialize(patient, PatientRead),
                "patient_history": prior_encounters,
                "returning_patient": returning,
            },
        )


class ClinicalNlpAgent(ClinicalAgent):
    name = "clinical_nlp"

    def run(self, state: ClinicalState) -> AgentOutput:
        normalized = [
            {
                "id": symptom["id"],
                "name": _normal_name(symptom["name"]),
                "severity": symptom.get("severity"),
                "duration": symptom.get("duration"),
                "onset": symptom.get("onset"),
                "present": symptom.get("present", True),
                "source": symptom.get("source"),
                "provenance": {
                    "source": symptom.get("source"),
                    "original_name": symptom["name"],
                },
            }
            for symptom in state.get("symptoms", [])
        ]
        text_supplied = any(
            state.get(field) for field in ("raw_text", "transcript", "ocr_text")
        )
        capabilities = {
            "structured_symptom_normalization": capability(
                CapabilityAvailability.AVAILABLE,
                "Stored symptom records are normalized with deterministic Python",
            ),
            "free_text_clinical_extraction": capability(
                CapabilityAvailability.AVAILABLE,
                "Versioned deterministic symptom extraction preserves explicit negation",
            ),
        }
        if not normalized:
            status = AgentExecutionStatus.PARTIAL
            summary = "No structured symptoms were available to normalize"
        elif text_supplied:
            status = AgentExecutionStatus.SUCCESS
            summary = "Normalized structured and speech-derived symptoms with provenance"
        else:
            status = AgentExecutionStatus.SUCCESS
            summary = f"Deterministically normalized {len(normalized)} structured symptoms"
        return AgentOutput(
            status=status,
            summary=summary,
            updates={"normalized_symptoms": normalized},
            capabilities=capabilities,
        )


class DataFusionAgent(ClinicalAgent):
    name = "data_fusion"

    def run(self, state: ClinicalState) -> AgentOutput:
        vitals = sorted(state.get("vitals", []), key=lambda item: item["measured_at"])
        labs = sorted(state.get("labs", []), key=lambda item: item["collected_at"])
        normalized_symptoms = state.get("normalized_symptoms", [])
        symptom_groups: dict[str, list[dict[str, Any]]] = {}
        for symptom in normalized_symptoms:
            symptom_groups.setdefault(_normal_name(symptom["name"]), []).append(symptom)
        current_symptoms: list[dict[str, Any]] = []
        for values in symptom_groups.values():
            manual = [item for item in values if item.get("source") == "MANUAL"]
            current_symptoms.append(manual[-1] if manual else values[-1])
        current_vitals = vitals[-1] if vitals else None
        labs_by_test: dict[str, list[dict[str, Any]]] = {}
        for lab in labs:
            labs_by_test.setdefault(_lab_key(lab["test_name"]), []).append(lab)
        current_labs: dict[str, dict[str, Any]] = {}
        for key, results in labs_by_test.items():
            manually_entered = [item for item in results if item.get("source") == "MANUAL"]
            current_labs[key] = manually_entered[-1] if manually_entered else results[-1]

        multimodal_conflicts = [
            conflict
            for result in [
                *state.get("document_results", []),
                *state.get("speech_results", []),
            ]
            for conflict in result.get("conflicts", [])
        ]

        provenance = {
            "symptoms": [
                {"id": item["id"], "source": item.get("source")} for item in state.get("symptoms", [])
            ],
            "vitals": [
                {
                    "id": item["id"],
                    "source": item.get("source"),
                    "measured_at": item["measured_at"],
                }
                for item in vitals
            ],
            "labs": [
                {
                    "id": item["id"],
                    "test_name": item["test_name"],
                    "source": item.get("source"),
                    "collected_at": item["collected_at"],
                }
                for item in labs
            ],
        }
        fused_context = {
            "patient": state.get("patient"),
            "returning_patient": state.get("returning_patient"),
            "previous_encounters": state.get("patient_history", []),
            "encounter": state.get("encounter"),
            "symptoms": current_symptoms,
            "all_symptom_observations": normalized_symptoms,
            "vitals": {
                "latest": current_vitals,
                "previous": vitals[:-1],
                "all_readings": vitals,
            },
            "labs": {
                "latest_by_test": current_labs,
                "all_results": labs,
            },
            "provenance": provenance,
            "multimodal_conflicts": multimodal_conflicts,
            "fusion_policy": {
                "manual_lab_precedence": True,
                "manual_symptom_precedence": True,
                "conflicting_observations_preserved": True,
            },
        }
        missing = list(state.get("missing_information", []))
        for key, value in (
            ("patient", state.get("patient")),
            ("normalized_symptoms", state.get("normalized_symptoms")),
            ("current_vitals", current_vitals),
            ("current_labs", current_labs),
        ):
            if not value:
                missing.append(key)
        status = AgentExecutionStatus.PARTIAL if missing else AgentExecutionStatus.SUCCESS
        return AgentOutput(
            status=status,
            summary=(
                f"Fused patient context, {len(vitals)} vital readings, and {len(labs)} lab results"
            ),
            updates={
                "current_vitals": current_vitals,
                "previous_vitals": vitals[:-1],
                "current_labs": current_labs,
                "fused_context": fused_context,
                "missing_information": list(dict.fromkeys(missing)),
            },
        )


class TriageRiskAgent(ClinicalAgent):
    name = "triage_risk"

    def __init__(
        self,
        session: Session,
        risk_tool: CardiacRiskTool | None = None,
        triage_tool: EmergencyTriageTool | None = None,
    ) -> None:
        self.risk_tool = risk_tool or CardiacRiskTool()
        self.triage_tool = triage_tool or EmergencyTriageTool()
        self.risk_persistence = RiskAssessmentPersistenceService(session)
        self.triage_persistence = TriageAssessmentPersistenceService(session)

    def run(self, state: ClinicalState) -> AgentOutput:
        feature_result = build_cardiac_features(state)
        if feature_result.missing_features:
            cardiac_risk = {
                "status": "INCOMPLETE_INPUT",
                "predicted_class": None,
                "prediction": None,
                "probability": None,
                "missing_features": feature_result.missing_features,
                "input_features": feature_result.features,
                "feature_source_snapshot": feature_result.source_snapshot,
                "reason": "Required cardiac model features are missing",
            }
            cardiac_capability = capability(
                CapabilityAvailability.PARTIAL,
                "Model is available but the clinical feature vector is incomplete",
                missing_features=feature_result.missing_features,
            )
        else:
            risk_result = self.risk_tool.predict(feature_result.features)
            if risk_result["status"] == "SUCCESS":
                prediction = self.risk_persistence.persist_prediction(
                    state["encounter_id"], risk_result
                )
                cardiac_risk = {
                    **risk_result,
                    "prediction_id": prediction.id,
                    "created_at": prediction.created_at.isoformat(),
                    "feature_source_snapshot": feature_result.source_snapshot,
                }
                cardiac_capability = capability(
                    CapabilityAvailability.AVAILABLE,
                    "Versioned local cardiac model inference completed",
                    model_version=risk_result["model_version"],
                    prediction_id=prediction.id,
                )
            else:
                cardiac_risk = {
                    **risk_result,
                    "predicted_class": None,
                    "prediction": None,
                    "probability": None,
                    "feature_source_snapshot": feature_result.source_snapshot,
                }
                cardiac_capability = capability(
                    (
                        CapabilityAvailability.PENDING_CAPABILITY
                        if risk_result["status"] == "PENDING_CAPABILITY"
                        else CapabilityAvailability.PARTIAL
                    ),
                    risk_result.get("reason", "Cardiac model is unavailable"),
                )

        triage_result = self.triage_tool.assess(
            state.get("fused_context"), cardiac_risk
        )
        persisted_triage = self.triage_persistence.persist(
            state["encounter_id"], triage_result
        )
        triage = {
            **triage_result,
            "assessment_id": persisted_triage.id,
            "created_at": persisted_triage.created_at.isoformat(),
        }
        missing_information = list(state.get("missing_information", []))
        missing_information.extend(
            f"cardiac_model_feature:{name}" for name in feature_result.missing_features
        )
        missing_information.extend(
            f"triage:{name}" for name in triage_result["missing_information"]
        )
        cardiac_complete = cardiac_risk.get("status") == "SUCCESS"
        return AgentOutput(
            status=(
                AgentExecutionStatus.SUCCESS
                if cardiac_complete
                else AgentExecutionStatus.PARTIAL
            ),
            summary=(
                "Generated independent cardiac-risk and provisional triage assessments"
                if cardiac_complete
                else "Generated provisional triage assessment; cardiac risk was unavailable"
            ),
            updates={
                "cardiac_risk": cardiac_risk,
                "triage": triage,
                "missing_information": list(dict.fromkeys(missing_information)),
            },
            warnings=feature_result.warnings,
            capabilities={
                "heart_attack_risk_model": cardiac_capability,
                "emergency_triage": capability(
                    CapabilityAvailability.AVAILABLE,
                    "Versioned deterministic prototype triage subset evaluated",
                    policy_name=triage_result["policy_name"],
                    policy_version=triage_result["policy_version"],
                    assessment_id=persisted_triage.id,
                    provisional=triage_result["provisional"],
                ),
            },
        )


class SafetyAgent(ClinicalAgent):
    name = "safety"

    def run(self, state: ClinicalState) -> AgentOutput:
        missing = list(dict.fromkeys(state.get("missing_information", [])))
        findings: list[dict[str, Any]] = []
        if missing:
            findings.append(
                {
                    "type": "MISSING_INFORMATION",
                    "severity": "WARNING",
                    "items": missing,
                }
            )
        vitals = state.get("current_vitals") or {}
        if (
            vitals.get("systolic_bp") is not None
            and vitals.get("diastolic_bp") is not None
            and vitals["systolic_bp"] < vitals["diastolic_bp"]
        ):
            findings.append(
                {
                    "type": "CONTRADICTORY_VITALS",
                    "severity": "WARNING",
                    "detail": "Latest systolic blood pressure is below diastolic blood pressure",
                }
            )
        if state.get("errors"):
            findings.append(
                {
                    "type": "UPSTREAM_ERRORS",
                    "severity": "ERROR",
                    "items": state["errors"],
                }
            )
        cardiac_risk = dict(state.get("cardiac_risk") or {})
        triage = dict(state.get("triage") or {})
        reasoning = dict(state.get("clinical_reasoning") or {})
        priority = dict(state.get("priority") or {})
        sanitized_updates: dict[str, Any] = {}
        if cardiac_risk.get("status") in {"PENDING_CAPABILITY", "INCOMPLETE_INPUT"} and any(
            cardiac_risk.get(key) is not None for key in ("prediction", "probability")
        ):
            findings.append(
                {
                    "type": "INCONSISTENT_UNAVAILABLE_RISK_OUTPUT",
                    "severity": "ERROR",
                    "detail": "Pending risk output contained a prediction and was cleared",
                }
            )
            cardiac_risk.update(prediction=None, probability=None)
            sanitized_updates["cardiac_risk"] = cardiac_risk
        if triage.get("status") in {
            "PENDING_CAPABILITY",
            "INCOMPLETE_INPUT",
            "INVALID_INPUT",
        } and any(
            triage.get(key) is not None
            for key in ("esi", "prototype_esi_level", "assigned_priority")
        ):
            findings.append(
                {
                    "type": "INCONSISTENT_UNAVAILABLE_TRIAGE_OUTPUT",
                    "severity": "ERROR",
                    "detail": "Pending triage output contained an assignment and was cleared",
                }
            )
            triage.update(esi=None, prototype_esi_level=None, assigned_priority=None)
            sanitized_updates["triage"] = triage
        if triage.get("status") and triage.get("status") != "SUCCESS":
            findings.append(
                {
                    "type": "UNAVAILABLE_TRIAGE_RESULT",
                    "severity": "WARNING",
                    "detail": f"Triage upstream status is {triage.get('status')}",
                }
            )
        if triage.get("severity_level") and not all(
            triage.get(key) for key in ("policy_name", "policy_version")
        ):
            findings.append(
                {
                    "type": "INCONSISTENT_TRIAGE_METADATA",
                    "severity": "ERROR",
                    "detail": "Triage severity exists without policy name and version",
                }
            )
        if triage.get("provisional"):
            findings.append(
                {
                    "type": "PROVISIONAL_TRIAGE",
                    "severity": "WARNING",
                    "detail": "Prototype triage requires clinician assessment",
                }
            )
        if triage.get("missing_information"):
            findings.append(
                {
                    "type": "TRIAGE_MISSING_INFORMATION",
                    "severity": "WARNING",
                    "items": triage["missing_information"],
                }
            )
        if priority.get("status") == "SUCCESS":
            if not DynamicPriorityPolicy.triage_is_usable(triage):
                findings.append(
                    {
                        "type": "PRIORITY_WITHOUT_USABLE_TRIAGE",
                        "severity": "ERROR",
                        "detail": "Operational priority exists without a usable triage assessment",
                    }
                )
            if not all(priority.get(key) for key in ("policy_name", "policy_version")):
                findings.append(
                    {
                        "type": "INCONSISTENT_PRIORITY_METADATA",
                        "severity": "ERROR",
                        "detail": "Queue priority exists without policy name and version",
                    }
                )
            valid_bands = {"CRITICAL", "VERY_HIGH", "HIGH", "MODERATE", "ROUTINE"}
            score = priority.get("priority_score")
            if (
                not isinstance(score, (int, float))
                or not 0 <= score <= 100
                or priority.get("priority_band") not in valid_bands
            ):
                findings.append(
                    {
                        "type": "INVALID_PRIORITY_VALUE",
                        "severity": "ERROR",
                        "detail": "Queue priority score or band is outside the policy contract",
                    }
                )
            if priority.get("provisional") is not bool(triage.get("provisional")):
                findings.append(
                    {
                        "type": "INCONSISTENT_PRIORITY_PROVISIONAL_FLAG",
                        "severity": "ERROR",
                        "detail": "Priority provisional flag differs from upstream triage",
                    }
                )
            stale_reasons: list[str] = []
            if priority.get("triage_assessment_id") != triage.get("assessment_id"):
                stale_reasons.append("triage_assessment")
            current_vital_id = (state.get("current_vitals") or {}).get("id")
            priority_vital_id = (priority.get("deterioration") or {}).get(
                "latest_vital_id"
            )
            if current_vital_id and priority_vital_id != current_vital_id:
                stale_reasons.append("latest_vital")
            if stale_reasons:
                findings.append(
                    {
                        "type": "STALE_PRIORITY",
                        "severity": "ERROR",
                        "items": stale_reasons,
                        "detail": "Queue priority references an older clinical snapshot",
                    }
                )
            if state.get("workflow_halted"):
                findings.append(
                    {
                        "type": "CRITICAL_UPSTREAM_FAILURE_WITH_PRIORITY",
                        "severity": "ERROR",
                        "detail": "A halted workflow must not silently produce queue priority",
                    }
                )
        if reasoning.get("status") and reasoning.get("status") != "SUCCESS":
            findings.append(
                {
                    "type": "CLINICAL_REASONING_UNAVAILABLE",
                    "severity": "WARNING",
                    "detail": (
                        f"Reasoning ended with {reasoning.get('termination_reason', reasoning.get('status'))}"
                    ),
                }
            )
        if reasoning.get("status") == "SUCCESS":
            metadata_fields = {
                "status",
                "result_id",
                "provider",
                "model",
                "agent_version",
                "schema_version",
                "termination_reason",
                "provider_latency_ms",
                "latency_ms",
                "retrieved_source_ids",
                "available_evidence_refs",
                "created_at",
            }
            raw_reasoning_text = " ".join(
                str(reasoning.get(field, "")) for field in ("summary", "uncertainty")
            )
            if re.search(
                r"\b(probability|likelihood|chance)\b[^.\n]{0,30}\b\d+(?:\.\d+)?\s*%?",
                raw_reasoning_text,
                re.IGNORECASE,
            ):
                findings.append(
                    {
                        "type": "INVENTED_NUMERIC_DISEASE_PROBABILITY",
                        "severity": "ERROR",
                        "detail": "Only the deterministic cardiac model may emit a numeric probability",
                    }
                )
            raw_kg = reasoning.get("knowledge_graph_evidence", [])
            if any(not item.get("source_id") or not item.get("edge_id") for item in raw_kg):
                findings.append(
                    {
                        "type": "KG_EVIDENCE_WITHOUT_PROVENANCE",
                        "severity": "ERROR",
                        "detail": "Knowledge graph evidence lacked a source or edge reference",
                    }
                )
            try:
                validated_reasoning = ClinicalReasoningOutput.model_validate(
                    {
                        key: value
                        for key, value in reasoning.items()
                        if key not in metadata_fields
                    }
                )
            except ValidationError:
                findings.append(
                    {
                        "type": "INVALID_CLINICAL_REASONING_OUTPUT",
                        "severity": "ERROR",
                        "detail": "Clinical reasoning did not match the validated schema",
                    }
                )
            else:
                available_refs = set(reasoning.get("available_evidence_refs", []))
                referenced = collect_output_evidence_refs(validated_reasoning)
                unsupported = sorted(referenced - available_refs)
                if unsupported:
                    findings.append(
                        {
                            "type": "UNGROUNDED_REASONING_REFERENCES",
                            "severity": "ERROR",
                            "items": unsupported,
                        }
                    )
                unreferenced_claims = [
                    item.condition
                    for item in validated_reasoning.differential_considerations
                    if item.supporting_findings and not item.evidence_refs
                ]
                if unreferenced_claims:
                    findings.append(
                        {
                            "type": "REASONING_CLAIMS_WITHOUT_EVIDENCE",
                            "severity": "ERROR",
                            "items": unreferenced_claims,
                        }
                    )
                retrieved = validated_reasoning.clinical_evidence
                retrieval_called = any(
                    item.tool == "retrieve_clinical_guidelines"
                    for item in validated_reasoning.tool_calls
                )
                if retrieval_called and not retrieved:
                    findings.append(
                        {
                            "type": "EMPTY_RAG_RETRIEVAL",
                            "severity": "WARNING",
                            "detail": "Guideline retrieval was called but returned no evidence",
                        }
                    )
                reasoning_text = " ".join(
                    [
                        validated_reasoning.summary,
                        validated_reasoning.uncertainty,
                        *(item.condition for item in validated_reasoning.differential_considerations),
                    ]
                )
                if re.search(
                    r"\b(definit(?:e|ely)|confirmed diagnosis|certainly|proves?)\b",
                    reasoning_text,
                    re.IGNORECASE,
                ):
                    findings.append(
                        {
                            "type": "EXCESSIVE_REASONING_CERTAINTY",
                            "severity": "ERROR",
                            "detail": "Reasoning used language inconsistent with differential considerations",
                        }
                    )
                deterministic_contradictions: list[str] = []
                if cardiac_risk.get("status") == "SUCCESS" and re.search(
                    r"cardiac (?:risk )?model (?:is |was )?(?:unavailable|not available)",
                    reasoning_text,
                    re.IGNORECASE,
                ):
                    deterministic_contradictions.append(
                        "Reasoning described the successful cardiac model as unavailable"
                    )
                if triage.get("status") == "SUCCESS" and re.search(
                    r"triage (?:is |was )?(?:unavailable|not available)",
                    reasoning_text,
                    re.IGNORECASE,
                ):
                    deterministic_contradictions.append(
                        "Reasoning described the successful triage result as unavailable"
                    )
                if deterministic_contradictions:
                    findings.append(
                        {
                            "type": "REASONING_DETERMINISTIC_CONTRADICTION",
                            "severity": "ERROR",
                            "items": deterministic_contradictions,
                            "detail": "Deterministic model and triage outputs remain authoritative",
                        }
                    )
                if re.search(
                    r"\b(probability|likelihood|chance)\b[^.\n]{0,30}\b\d+(?:\.\d+)?\s*%?",
                    reasoning_text,
                    re.IGNORECASE,
                ):
                    findings.append(
                        {
                            "type": "INVENTED_NUMERIC_DISEASE_PROBABILITY",
                            "severity": "ERROR",
                            "detail": "Only the deterministic cardiac model may emit a numeric probability",
                        }
                    )
        capabilities = {
            "deterministic_completeness_checks": capability(
                CapabilityAvailability.AVAILABLE,
                "Checks use only current structured state",
            ),
            "drug_interactions": capability(
                CapabilityAvailability.PENDING_CAPABILITY,
                "Medication data and interaction knowledge sources are unavailable",
            ),
            "contraindications": capability(
                CapabilityAvailability.PENDING_CAPABILITY,
                "Contraindication knowledge sources are unavailable",
            ),
            "cross_agent_conflict_detection": capability(
                CapabilityAvailability.PARTIAL,
                "Reasoning grounding and obvious-certainty checks are implemented; deterministic outputs remain authoritative",
            ),
            "priority_validation": capability(
                CapabilityAvailability.AVAILABLE,
                "Validates policy metadata, values, provisional state, and source-snapshot freshness without assigning priority",
            ),
        }
        return AgentOutput(
            status=(AgentExecutionStatus.PARTIAL if findings else AgentExecutionStatus.SUCCESS),
            summary=f"Completed deterministic safety checks with {len(findings)} findings",
            updates={
                **sanitized_updates,
                "safety_findings": {
                    "status": "COMPLETE",
                    "findings": findings,
                    "checked_upstream_errors": True,
                }
            },
            capabilities=capabilities,
        )


class XaiAgent(ClinicalAgent):
    name = "xai"

    def __init__(
        self, session: Session, explanation_tool: ShapExplanationTool | None = None
    ) -> None:
        self.explanation_tool = explanation_tool
        self.persistence = RiskAssessmentPersistenceService(session)

    def run(self, state: ClinicalState) -> AgentOutput:
        cardiac_risk = state.get("cardiac_risk") or {}
        triage = state.get("triage") or {}
        reasoning = state.get("clinical_reasoning") or {}
        priority = state.get("priority") or {}
        prediction_id = cardiac_risk.get("prediction_id")
        decision_trace = [
            {
                "agent": entry.get("agent"),
                "status": entry.get("status"),
                "summary": entry.get("summary"),
                "completed_at": entry.get("completed_at"),
            }
            for entry in state.get("agent_trace", [])
        ]
        decision_trace_capability = capability(
            CapabilityAvailability.AVAILABLE,
            "Generated deterministically from actual workflow trace entries",
            entry_count=len(decision_trace),
        )
        triage_rule_trace = {
            "policy_name": triage.get("policy_name"),
            "policy_version": triage.get("policy_version"),
            "severity_level": triage.get("severity_level"),
            "provisional": triage.get("provisional"),
            "triggered_rule_ids": triage.get("triggered_rule_ids", []),
            "rules": triage.get("rule_hits", []),
            "missing_information": triage.get("missing_information", []),
        }
        clinical_reasoning_evidence = {
            "status": reasoning.get("status"),
            "provider": reasoning.get("provider"),
            "model": reasoning.get("model"),
            "termination_reason": reasoning.get("termination_reason"),
            "tool_calls": reasoning.get("tool_calls", []),
            "clinical_evidence": reasoning.get("clinical_evidence", []),
            "knowledge_graph_evidence": reasoning.get(
                "knowledge_graph_evidence", []
            ),
            "differential_considerations": reasoning.get(
                "differential_considerations", []
            ),
            "limitations": reasoning.get("limitations", []),
        }
        priority_rule_trace = {
            "status": priority.get("status"),
            "policy_name": priority.get("policy_name"),
            "policy_version": priority.get("policy_version"),
            "priority_score": priority.get("priority_score"),
            "priority_band": priority.get("priority_band"),
            "reason_codes": priority.get("reason_codes", []),
            "deterioration_status": priority.get("deterioration_status"),
            "provisional": priority.get("provisional"),
            "rules": priority.get("rule_trace", []),
        }
        if not prediction_id:
            reason = "No persisted upstream cardiac prediction exists"
            return AgentOutput(
                status=AgentExecutionStatus.PARTIAL,
                summary="Generated a decision trace; SHAP requires a cardiac prediction",
                updates={
                    "explanation": {
                        "status": "PARTIAL",
                        "upstream_prediction_available": False,
                        "prediction_id": None,
                        "model_contributions": None,
                        "feature_contributions": None,
                        "shap_values": None,
                        "triage_rule_trace": triage_rule_trace,
                        "clinical_reasoning_evidence": clinical_reasoning_evidence,
                        "priority_rule_trace": priority_rule_trace,
                        "clinical_evidence": reasoning.get("clinical_evidence", []),
                        "counterfactual": None,
                        "decision_trace": decision_trace,
                        "imaging_saliency": None,
                        "reason": reason,
                    }
                },
                capabilities={
                    "shap": capability(CapabilityAvailability.PENDING_CAPABILITY, reason),
                    "triage_rule_trace": capability(
                        CapabilityAvailability.AVAILABLE,
                        "Deterministic triage policy trace is separate from model contributions",
                        policy_version=triage.get("policy_version"),
                    ),
                    "clinical_evidence": capability(
                        (
                            CapabilityAvailability.AVAILABLE
                            if reasoning.get("status") == "SUCCESS"
                            else CapabilityAvailability.PARTIAL
                        ),
                        "Clinical reasoning evidence remains separate from SHAP and triage rules",
                    ),
                    "priority_rule_trace": capability(
                        (
                            CapabilityAvailability.AVAILABLE
                            if priority.get("status") == "SUCCESS"
                            else CapabilityAvailability.PARTIAL
                        ),
                        "Deterministic queue rules remain separate from SHAP, triage, and reasoning",
                        policy_version=priority.get("policy_version"),
                    ),
                    "counterfactual": capability(
                        CapabilityAvailability.PENDING_CAPABILITY,
                        "Counterfactual explanation is not implemented",
                    ),
                    "imaging_saliency": capability(
                        CapabilityAvailability.PENDING_CAPABILITY,
                        "Imaging saliency is not implemented",
                    ),
                    "decision_trace": decision_trace_capability,
                },
            )

        tool = self.explanation_tool or ShapExplanationTool()
        shap_result = tool.explain(cardiac_risk["input_features"])
        explanation = self.persistence.persist_explanation(prediction_id, shap_result)
        capabilities = {
            "shap": capability(
                CapabilityAvailability.AVAILABLE,
                "Tree SHAP model feature contributions were generated",
                explanation_id=explanation.id,
            ),
            "triage_rule_trace": capability(
                CapabilityAvailability.AVAILABLE,
                "Deterministic triage policy trace is separate from model contributions",
                policy_version=triage.get("policy_version"),
            ),
            "clinical_evidence": capability(
                (
                    CapabilityAvailability.AVAILABLE
                    if reasoning.get("status") == "SUCCESS"
                    else CapabilityAvailability.PARTIAL
                ),
                "Clinical reasoning evidence remains separate from SHAP and triage rules",
            ),
            "priority_rule_trace": capability(
                (
                    CapabilityAvailability.AVAILABLE
                    if priority.get("status") == "SUCCESS"
                    else CapabilityAvailability.PARTIAL
                ),
                "Deterministic queue rules remain separate from SHAP, triage, and reasoning",
                policy_version=priority.get("policy_version"),
            ),
            "counterfactual": capability(
                CapabilityAvailability.PENDING_CAPABILITY,
                "Counterfactual explanation is not implemented",
            ),
            "imaging_saliency": capability(
                CapabilityAvailability.PENDING_CAPABILITY,
                "Imaging saliency is not implemented",
            ),
            "decision_trace": decision_trace_capability,
        }
        return AgentOutput(
            status=AgentExecutionStatus.PARTIAL,
            summary="Generated and persisted SHAP model feature contributions and decision trace",
            updates={
                "explanation": {
                    "status": "PARTIAL",
                    "upstream_prediction_available": True,
                    "explanation_id": explanation.id,
                    "generated_at": explanation.generated_at.isoformat(),
                    "prediction_id": prediction_id,
                    "method": shap_result["method"],
                    "explainer_version": shap_result["explainer_version"],
                    "model_version": shap_result["model_version"],
                    "base_value": shap_result["base_value"],
                    "model_contributions": {
                        "model_version": cardiac_risk["model_version"],
                        "probability": cardiac_risk["probability"],
                        "method": shap_result["method"],
                        "feature_contributions": shap_result["feature_contributions"],
                    },
                    "feature_contributions": shap_result["feature_contributions"],
                    "top_contributors": shap_result["top_contributors"],
                    "shap_values": shap_result["feature_contributions"],
                    "triage_rule_trace": triage_rule_trace,
                    "explanation_latency_ms": shap_result["explanation_latency_ms"],
                    "clinical_reasoning_evidence": clinical_reasoning_evidence,
                    "priority_rule_trace": priority_rule_trace,
                    "clinical_evidence": reasoning.get("clinical_evidence", []),
                    "counterfactual": None,
                    "decision_trace": decision_trace,
                    "imaging_saliency": None,
                    "disclaimer": shap_result["disclaimer"],
                }
            },
            capabilities=capabilities,
        )


class PriorityAgent(ClinicalAgent):
    name = "priority"

    def __init__(
        self,
        session: Session,
        service: DynamicQueueService | None = None,
    ) -> None:
        self.service = service or DynamicQueueService(session)

    def run(self, state: ClinicalState) -> AgentOutput:
        triage = state.get("triage") or {}
        if not DynamicPriorityPolicy.triage_is_usable(triage):
            reason = "A successful, determinate, persisted triage assessment is required"
            return AgentOutput(
                status=AgentExecutionStatus.PARTIAL,
                summary="Queue priority remains pending because usable triage is unavailable",
                updates={
                    "priority": {
                        "status": "PENDING_TRIAGE",
                        "queue_entry_id": None,
                        "priority_score": None,
                        "priority_band": None,
                        "valid_triage_available": False,
                        "reason": reason,
                    }
                },
                capabilities={
                    "dynamic_priority_queue": capability(
                        CapabilityAvailability.PARTIAL, reason
                    )
                },
            )

        encounter = state.get("encounter") or {}
        try:
            result = self.service.recalculate(
                encounter_id=state["encounter_id"],
                patient_id=state["patient_id"],
                triage=triage,
                cardiac_risk=state.get("cardiac_risk"),
                vital_history=state.get("vitals", []),
                waiting_since=encounter.get("started_at"),
            )
        except Exception:
            self.service.session.rollback()
            raise
        return AgentOutput(
            status=AgentExecutionStatus.SUCCESS,
            summary=(
                f"Calculated {result['priority_band']} operational queue priority "
                f"with score {result['priority_score']:.1f}"
            ),
            updates={"priority": {**result, "valid_triage_available": True}},
            capabilities={
                "dynamic_priority_queue": capability(
                    CapabilityAvailability.AVAILABLE,
                    "Versioned deterministic queue priority was calculated and persisted",
                    policy_name=result["policy_name"],
                    policy_version=result["policy_version"],
                    queue_entry_id=result["queue_entry_id"],
                )
            },
        )

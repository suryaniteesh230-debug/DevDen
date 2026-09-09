from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    EncounterStatus,
    ObservationSource,
    PriorityBand,
    QueueStatus,
    StaffRole,
)
from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def uuid_string() -> str:
    return str(uuid4())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class StaffUser(Base):
    __tablename__ = "staff_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[StaffRole] = mapped_column(
        Enum(StaffRole, native_enum=False), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class Patient(TimestampMixin, Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    external_patient_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), index=True)
    last_name: Mapped[str] = mapped_column(String(100), index=True)
    date_of_birth: Mapped[date] = mapped_column(Date)
    gender: Mapped[str] = mapped_column(String(50))
    phone_number: Mapped[str | None] = mapped_column(String(30), nullable=True)

    encounters: Mapped[list[ClinicalEncounter]] = relationship(
        back_populates="patient", cascade="all, delete-orphan"
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(back_populates="patient")


class ClinicalEncounter(TimestampMixin, Base):
    __tablename__ = "clinical_encounters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    encounter_type: Mapped[str] = mapped_column(String(80))
    chief_complaint: Mapped[str] = mapped_column(Text)
    clinician_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EncounterStatus] = mapped_column(
        Enum(EncounterStatus, native_enum=False), default=EncounterStatus.ACTIVE, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    patient: Mapped[Patient] = relationship(back_populates="encounters")
    symptoms: Mapped[list[Symptom]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan", order_by="Symptom.created_at"
    )
    vital_signs: Mapped[list[VitalSigns]] = relationship(
        back_populates="encounter",
        cascade="all, delete-orphan",
        order_by="VitalSigns.measured_at",
    )
    lab_results: Mapped[list[LabResult]] = relationship(
        back_populates="encounter",
        cascade="all, delete-orphan",
        order_by="LabResult.collected_at",
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(back_populates="encounter")
    risk_predictions: Mapped[list[RiskPrediction]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    triage_assessments: Mapped[list[TriageAssessment]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    clinical_reasoning_results: Mapped[list[ClinicalReasoningResult]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    queue_entry: Mapped[QueueEntry | None] = relationship(
        back_populates="encounter", cascade="all, delete-orphan", uselist=False
    )
    documents: Mapped[list[ClinicalDocument]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )
    speech_transcriptions: Mapped[list[SpeechTranscription]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_encounters_patient_started", "patient_id", "started_at"),)


class Symptom(Base):
    __tablename__ = "symptoms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120))
    severity: Mapped[int | None] = mapped_column(nullable=True)
    duration: Mapped[str | None] = mapped_column(String(100), nullable=True)
    onset: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    present: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[ObservationSource] = mapped_column(Enum(ObservationSource, native_enum=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    encounter: Mapped[ClinicalEncounter] = relationship(back_populates="symptoms")


class VitalSigns(Base):
    __tablename__ = "vital_signs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="CASCADE"), index=True
    )
    heart_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    systolic_bp: Mapped[float | None] = mapped_column(Float, nullable=True)
    diastolic_bp: Mapped[float | None] = mapped_column(Float, nullable=True)
    spo2: Mapped[float | None] = mapped_column(Float, nullable=True)
    respiratory_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    source: Mapped[ObservationSource] = mapped_column(Enum(ObservationSource, native_enum=False))

    encounter: Mapped[ClinicalEncounter] = relationship(back_populates="vital_signs")

    __table_args__ = (Index("ix_vitals_encounter_measured", "encounter_id", "measured_at"),)


class LabResult(Base):
    __tablename__ = "lab_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="CASCADE"), index=True
    )
    test_name: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    source: Mapped[ObservationSource] = mapped_column(Enum(ObservationSource, native_enum=False))
    reference_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    encounter: Mapped[ClinicalEncounter] = relationship(back_populates="lab_results")

    __table_args__ = (Index("ix_labs_encounter_collected", "encounter_id", "collected_at"),)


class RiskPrediction(Base):
    __tablename__ = "risk_predictions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="CASCADE"), index=True
    )
    model_name: Mapped[str] = mapped_column(String(120))
    model_version: Mapped[str] = mapped_column(String(120), index=True)
    predicted_class: Mapped[int] = mapped_column()
    probability: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    input_feature_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    inference_latency_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    encounter: Mapped[ClinicalEncounter] = relationship(back_populates="risk_predictions")
    explanations: Mapped[list[Explanation]] = relationship(
        back_populates="prediction", cascade="all, delete-orphan"
    )


class Explanation(Base):
    __tablename__ = "explanations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    prediction_id: Mapped[str] = mapped_column(
        ForeignKey("risk_predictions.id", ondelete="CASCADE"), index=True
    )
    explanation_method: Mapped[str] = mapped_column(String(80))
    explainer_version: Mapped[str] = mapped_column(String(120))
    model_version: Mapped[str] = mapped_column(String(120))
    feature_contributions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    counterfactual: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    clinical_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    saliency: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    prediction: Mapped[RiskPrediction] = relationship(back_populates="explanations")


class TriageAssessment(Base):
    __tablename__ = "triage_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="CASCADE"), index=True
    )
    policy_name: Mapped[str] = mapped_column(String(160))
    policy_version: Mapped[str] = mapped_column(String(120), index=True)
    severity_level: Mapped[str] = mapped_column(String(80))
    provisional: Mapped[bool] = mapped_column(Boolean)
    completeness_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    confidence_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    rule_hits: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    missing_information: Mapped[list[str]] = mapped_column(JSON)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    evaluation_latency_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    encounter: Mapped[ClinicalEncounter] = relationship(back_populates="triage_assessments")


class ClinicalReasoningResult(Base):
    __tablename__ = "clinical_reasoning_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="CASCADE"), index=True
    )
    workflow_id: Mapped[str] = mapped_column(String(36), index=True)
    agent_name: Mapped[str] = mapped_column(String(120))
    agent_version: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(160))
    schema_version: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(Text)
    structured_output: Mapped[dict[str, Any]] = mapped_column(JSON)
    retrieved_source_ids: Mapped[list[str]] = mapped_column(JSON)
    knowledge_graph_evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    tool_call_trace: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    termination_reason: Mapped[str] = mapped_column(String(80), index=True)
    latency_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    encounter: Mapped[ClinicalEncounter] = relationship(
        back_populates="clinical_reasoning_results"
    )


class QueueEntry(TimestampMixin, Base):
    __tablename__ = "queue_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="CASCADE"), unique=True, index=True
    )
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), index=True
    )
    queue_status: Mapped[QueueStatus] = mapped_column(
        Enum(QueueStatus, native_enum=False), default=QueueStatus.WAITING, index=True
    )
    priority_score: Mapped[float] = mapped_column(Float)
    priority_band: Mapped[PriorityBand] = mapped_column(
        Enum(PriorityBand, native_enum=False), index=True
    )
    policy_name: Mapped[str] = mapped_column(String(160))
    policy_version: Mapped[str] = mapped_column(String(120), index=True)
    triage_assessment_id: Mapped[str] = mapped_column(
        ForeignKey("triage_assessments.id", ondelete="RESTRICT"), index=True
    )
    risk_prediction_id: Mapped[str | None] = mapped_column(
        ForeignKey("risk_predictions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reason_codes: Mapped[list[str]] = mapped_column(JSON)
    rule_trace: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    deterioration_status: Mapped[str] = mapped_column(String(40))
    waiting_since: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_recalculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

    encounter: Mapped[ClinicalEncounter] = relationship(back_populates="queue_entry")
    calculations: Mapped[list[QueuePriorityCalculation]] = relationship(
        back_populates="queue_entry",
        cascade="all, delete-orphan",
        order_by="QueuePriorityCalculation.calculated_at",
    )

    __table_args__ = (
        Index(
            "ix_queue_entries_active_order",
            "queue_status",
            "priority_score",
            "waiting_since",
            "created_at",
        ),
    )


class QueuePriorityCalculation(Base):
    __tablename__ = "queue_priority_calculations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    queue_entry_id: Mapped[str] = mapped_column(
        ForeignKey("queue_entries.id", ondelete="CASCADE"), index=True
    )
    triage_assessment_id: Mapped[str] = mapped_column(
        ForeignKey("triage_assessments.id", ondelete="RESTRICT"), index=True
    )
    risk_prediction_id: Mapped[str | None] = mapped_column(
        ForeignKey("risk_predictions.id", ondelete="SET NULL"), nullable=True
    )
    policy_name: Mapped[str] = mapped_column(String(160))
    policy_version: Mapped[str] = mapped_column(String(120), index=True)
    priority_score: Mapped[float] = mapped_column(Float)
    priority_band: Mapped[PriorityBand] = mapped_column(
        Enum(PriorityBand, native_enum=False)
    )
    reason_codes: Mapped[list[str]] = mapped_column(JSON)
    rule_trace: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    input_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    deterioration_status: Mapped[str] = mapped_column(String(40))
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

    queue_entry: Mapped[QueueEntry] = relationship(back_populates="calculations")


class ClinicalDocument(Base):
    __tablename__ = "clinical_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    safe_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[ObservationSource] = mapped_column(
        Enum(ObservationSource, native_enum=False), default=ObservationSource.OCR
    )
    processing_status: Mapped[str] = mapped_column(String(40), index=True)
    ocr_text: Mapped[str] = mapped_column(Text)
    ocr_engine: Mapped[str] = mapped_column(String(100))
    ocr_engine_version: Mapped[str] = mapped_column(String(120))
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extracted_fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    conflicts: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    lab_result_ids: Mapped[list[str]] = mapped_column(JSON)
    page_count: Mapped[int] = mapped_column(default=1)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

    encounter: Mapped[ClinicalEncounter] = relationship(back_populates="documents")

    __table_args__ = (
        Index("ix_clinical_documents_encounter_created", "encounter_id", "created_at"),
    )


class SpeechTranscription(Base):
    __tablename__ = "speech_transcriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    encounter_id: Mapped[str] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    safe_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column()
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[ObservationSource] = mapped_column(
        Enum(ObservationSource, native_enum=False), default=ObservationSource.SPEECH
    )
    processing_status: Mapped[str] = mapped_column(String(40), index=True)
    transcript: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(160))
    language: Mapped[str] = mapped_column(String(20))
    confidence_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    extracted_symptoms: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    conflicts: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    symptom_ids: Mapped[list[str]] = mapped_column(JSON)
    transcription_latency_ms: Mapped[float] = mapped_column(Float)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )

    encounter: Mapped[ClinicalEncounter] = relationship(
        back_populates="speech_transcriptions"
    )

    __table_args__ = (
        Index("ix_speech_transcriptions_encounter_created", "encounter_id", "created_at"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_string)
    encounter_id: Mapped[str | None] = mapped_column(
        ForeignKey("clinical_encounters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    patient_id: Mapped[str | None] = mapped_column(
        ForeignKey("patients.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    actor: Mapped[str] = mapped_column(String(120))
    action: Mapped[str] = mapped_column(String(255))
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)

    encounter: Mapped[ClinicalEncounter | None] = relationship(back_populates="audit_events")
    patient: Mapped[Patient | None] = relationship(back_populates="audit_events")

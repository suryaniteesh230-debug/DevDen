from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import EncounterStatus
from app.db.models import (
    AuditEvent,
    ClinicalDocument,
    ClinicalEncounter,
    ClinicalReasoningResult,
    Explanation,
    LabResult,
    Patient,
    QueueEntry,
    QueuePriorityCalculation,
    RiskPrediction,
    SpeechTranscription,
    Symptom,
    TriageAssessment,
    VitalSigns,
)


class PatientRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, patient: Patient) -> Patient:
        self.session.add(patient)
        self.session.flush()
        return patient

    def get(self, patient_id: str) -> Patient | None:
        return self.session.get(Patient, patient_id)

    def get_by_external_id(self, external_patient_id: str) -> Patient | None:
        statement = select(Patient).where(Patient.external_patient_id == external_patient_id)
        return self.session.scalar(statement)

    def search(
        self, external_patient_id: str | None, name: str | None, limit: int
    ) -> list[Patient]:
        statement = select(Patient).order_by(Patient.last_name, Patient.first_name)
        if external_patient_id:
            statement = statement.where(Patient.external_patient_id == external_patient_id)
        if name:
            pattern = f"%{name.lower()}%"
            full_name = func.lower(Patient.first_name + " " + Patient.last_name)
            statement = statement.where(
                or_(
                    func.lower(Patient.first_name).like(pattern),
                    func.lower(Patient.last_name).like(pattern),
                    full_name.like(pattern),
                )
            )
        return list(self.session.scalars(statement.limit(limit)).all())


class EncounterRepository:
    _detail_options = (
        selectinload(ClinicalEncounter.symptoms),
        selectinload(ClinicalEncounter.vital_signs),
        selectinload(ClinicalEncounter.lab_results),
    )

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, encounter: ClinicalEncounter) -> ClinicalEncounter:
        self.session.add(encounter)
        self.session.flush()
        return encounter

    def get(self, encounter_id: str, *, with_details: bool = False) -> ClinicalEncounter | None:
        statement = select(ClinicalEncounter).where(ClinicalEncounter.id == encounter_id)
        if with_details:
            statement = statement.options(*self._detail_options)
        return self.session.scalar(statement)

    def history_for_patient(self, patient_id: str) -> list[ClinicalEncounter]:
        statement = (
            select(ClinicalEncounter)
            .where(ClinicalEncounter.patient_id == patient_id)
            .options(*self._detail_options)
            .order_by(ClinicalEncounter.started_at.desc())
        )
        return list(self.session.scalars(statement).all())


class ObservationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_symptom(self, symptom: Symptom) -> Symptom:
        self.session.add(symptom)
        self.session.flush()
        return symptom

    def list_symptoms(self, encounter_id: str) -> list[Symptom]:
        statement = (
            select(Symptom)
            .where(Symptom.encounter_id == encounter_id)
            .order_by(Symptom.created_at)
        )
        return list(self.session.scalars(statement).all())

    def add_vitals(self, vitals: VitalSigns) -> VitalSigns:
        self.session.add(vitals)
        self.session.flush()
        return vitals

    def list_vitals(self, encounter_id: str) -> list[VitalSigns]:
        statement = (
            select(VitalSigns)
            .where(VitalSigns.encounter_id == encounter_id)
            .order_by(VitalSigns.measured_at)
        )
        return list(self.session.scalars(statement).all())

    def add_lab(self, lab: LabResult) -> LabResult:
        self.session.add(lab)
        self.session.flush()
        return lab

    def list_labs(self, encounter_id: str) -> list[LabResult]:
        statement = (
            select(LabResult)
            .where(LabResult.encounter_id == encounter_id)
            .order_by(LabResult.collected_at)
        )
        return list(self.session.scalars(statement).all())


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, event: AuditEvent) -> AuditEvent:
        self.session.add(event)
        self.session.flush()
        return event

    def list_for_workflow(self, workflow_id: str) -> list[AuditEvent]:
        statement = (
            select(AuditEvent)
            .where(AuditEvent.event_metadata["workflow_id"].as_string() == workflow_id)
            .order_by(AuditEvent.timestamp)
        )
        return list(self.session.scalars(statement).all())


class RiskPredictionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, prediction: RiskPrediction) -> RiskPrediction:
        self.session.add(prediction)
        self.session.flush()
        return prediction

    def get(self, prediction_id: str) -> RiskPrediction | None:
        return self.session.get(RiskPrediction, prediction_id)

    def list_for_encounter(self, encounter_id: str) -> list[RiskPrediction]:
        statement = (
            select(RiskPrediction)
            .where(RiskPrediction.encounter_id == encounter_id)
            .order_by(RiskPrediction.created_at)
        )
        return list(self.session.scalars(statement).all())


class ExplanationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, explanation: Explanation) -> Explanation:
        self.session.add(explanation)
        self.session.flush()
        return explanation

    def list_for_prediction(self, prediction_id: str) -> list[Explanation]:
        statement = (
            select(Explanation)
            .where(Explanation.prediction_id == prediction_id)
            .order_by(Explanation.generated_at)
        )
        return list(self.session.scalars(statement).all())


class TriageAssessmentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, assessment: TriageAssessment) -> TriageAssessment:
        self.session.add(assessment)
        self.session.flush()
        return assessment

    def get(self, assessment_id: str) -> TriageAssessment | None:
        return self.session.get(TriageAssessment, assessment_id)

    def list_for_encounter(self, encounter_id: str) -> list[TriageAssessment]:
        statement = (
            select(TriageAssessment)
            .where(TriageAssessment.encounter_id == encounter_id)
            .order_by(TriageAssessment.created_at, TriageAssessment.id)
        )
        return list(self.session.scalars(statement).all())


class ClinicalReasoningResultRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, result: ClinicalReasoningResult) -> ClinicalReasoningResult:
        self.session.add(result)
        self.session.flush()
        return result

    def get(self, result_id: str) -> ClinicalReasoningResult | None:
        return self.session.get(ClinicalReasoningResult, result_id)

    def list_for_encounter(self, encounter_id: str) -> list[ClinicalReasoningResult]:
        statement = (
            select(ClinicalReasoningResult)
            .where(ClinicalReasoningResult.encounter_id == encounter_id)
            .order_by(ClinicalReasoningResult.created_at, ClinicalReasoningResult.id)
        )
        return list(self.session.scalars(statement).all())


class QueueEntryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entry: QueueEntry) -> QueueEntry:
        self.session.add(entry)
        self.session.flush()
        return entry

    def get(self, queue_entry_id: str) -> QueueEntry | None:
        return self.session.get(QueueEntry, queue_entry_id)

    def get_for_encounter(self, encounter_id: str) -> QueueEntry | None:
        return self.session.scalar(
            select(QueueEntry).where(QueueEntry.encounter_id == encounter_id)
        )

    def list(self, *, status: object | None = None) -> list[QueueEntry]:
        statement = select(QueueEntry).options(
            selectinload(QueueEntry.encounter).selectinload(ClinicalEncounter.patient),
            selectinload(QueueEntry.calculations),
        )
        if status is not None:
            statement = statement.where(QueueEntry.queue_status == status)
        statement = statement.order_by(
            QueueEntry.priority_score.desc(),
            QueueEntry.waiting_since.asc(),
            QueueEntry.created_at.asc(),
            QueueEntry.id.asc(),
        )
        return list(self.session.scalars(statement).all())

    def list_pending_intake(self) -> list[tuple[Patient, ClinicalEncounter | None]]:
        """Return new registrations and active encounters not yet ranked."""
        active_unranked = (
            select(ClinicalEncounter)
            .outerjoin(QueueEntry, QueueEntry.encounter_id == ClinicalEncounter.id)
            .where(
                ClinicalEncounter.patient_id == Patient.id,
                ClinicalEncounter.status == EncounterStatus.ACTIVE,
                QueueEntry.id.is_(None),
            )
            .exists()
        )
        has_any_encounter = (
            select(ClinicalEncounter.id)
            .where(ClinicalEncounter.patient_id == Patient.id)
            .exists()
        )
        patients = list(
            self.session.scalars(
                select(Patient)
                .where(or_(~has_any_encounter, active_unranked))
                .order_by(Patient.created_at.asc(), Patient.id.asc())
            ).all()
        )

        result: list[tuple[Patient, ClinicalEncounter | None]] = []
        for patient in patients:
            encounter = self.session.scalar(
                select(ClinicalEncounter)
                .outerjoin(QueueEntry, QueueEntry.encounter_id == ClinicalEncounter.id)
                .where(
                    ClinicalEncounter.patient_id == patient.id,
                    ClinicalEncounter.status == EncounterStatus.ACTIVE,
                    QueueEntry.id.is_(None),
                )
                .order_by(ClinicalEncounter.started_at.desc(), ClinicalEncounter.id.desc())
                .limit(1)
            )
            result.append((patient, encounter))
        return result


class QueuePriorityCalculationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, calculation: QueuePriorityCalculation) -> QueuePriorityCalculation:
        self.session.add(calculation)
        self.session.flush()
        return calculation

    def list_for_entry(self, queue_entry_id: str) -> list[QueuePriorityCalculation]:
        statement = (
            select(QueuePriorityCalculation)
            .where(QueuePriorityCalculation.queue_entry_id == queue_entry_id)
            .order_by(
                QueuePriorityCalculation.calculated_at,
                QueuePriorityCalculation.id,
            )
        )
        return list(self.session.scalars(statement).all())


class ClinicalDocumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, document: ClinicalDocument) -> ClinicalDocument:
        self.session.add(document)
        self.session.flush()
        return document

    def get(self, document_id: str) -> ClinicalDocument | None:
        return self.session.get(ClinicalDocument, document_id)

    def list_for_encounter(self, encounter_id: str) -> list[ClinicalDocument]:
        statement = (
            select(ClinicalDocument)
            .where(ClinicalDocument.encounter_id == encounter_id)
            .order_by(ClinicalDocument.created_at, ClinicalDocument.id)
        )
        return list(self.session.scalars(statement).all())


class SpeechTranscriptionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, transcription: SpeechTranscription) -> SpeechTranscription:
        self.session.add(transcription)
        self.session.flush()
        return transcription

    def get(self, transcription_id: str) -> SpeechTranscription | None:
        return self.session.get(SpeechTranscription, transcription_id)

    def list_for_encounter(self, encounter_id: str) -> list[SpeechTranscription]:
        statement = (
            select(SpeechTranscription)
            .where(SpeechTranscription.encounter_id == encounter_id)
            .order_by(SpeechTranscription.created_at, SpeechTranscription.id)
        )
        return list(self.session.scalars(statement).all())

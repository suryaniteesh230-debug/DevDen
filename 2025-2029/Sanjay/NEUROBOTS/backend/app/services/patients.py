from sqlalchemy.orm import Session

from app.core.exceptions import DuplicateEntityError, EntityNotFoundError
from app.db.models import Patient
from app.repositories.clinical import EncounterRepository, PatientRepository
from app.schemas.clinical import PatientCreate
from app.services.audit import record_audit_event


class PatientService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.patients = PatientRepository(session)
        self.encounters = EncounterRepository(session)

    def create(self, payload: PatientCreate, *, actor: str = "kiosk-user") -> Patient:
        if self.patients.get_by_external_id(payload.external_patient_id):
            raise DuplicateEntityError(
                f"external patient ID '{payload.external_patient_id}' already exists"
            )
        patient = self.patients.add(Patient(**payload.model_dump()))
        record_audit_event(
            self.session,
            event_type="PATIENT_CREATED",
            action="Created patient record",
            actor=actor,
            patient_id=patient.id,
        )
        self.session.commit()
        self.session.refresh(patient)
        return patient

    def get(self, patient_id: str) -> Patient:
        patient = self.patients.get(patient_id)
        if patient is None:
            raise EntityNotFoundError("patient", patient_id)
        return patient

    def search(
        self, external_patient_id: str | None, name: str | None, limit: int
    ) -> list[Patient]:
        return self.patients.search(external_patient_id, name, limit)

    def history(self, patient_id: str):
        patient = self.get(patient_id)
        return patient, self.encounters.history_for_patient(patient_id)

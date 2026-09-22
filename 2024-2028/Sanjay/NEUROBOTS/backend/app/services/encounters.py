from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.enums import EncounterStatus
from app.core.exceptions import EntityNotFoundError
from app.db.models import ClinicalEncounter
from app.repositories.clinical import EncounterRepository, PatientRepository
from app.schemas.clinical import EncounterCreate, EncounterUpdate
from app.services.audit import record_audit_event


class EncounterService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.encounters = EncounterRepository(session)
        self.patients = PatientRepository(session)

    def create(
        self, patient_id: str, payload: EncounterCreate, *, actor: str = "kiosk-user"
    ) -> ClinicalEncounter:
        if self.patients.get(patient_id) is None:
            raise EntityNotFoundError("patient", patient_id)
        encounter = self.encounters.add(
            ClinicalEncounter(patient_id=patient_id, **payload.model_dump())
        )
        record_audit_event(
            self.session,
            event_type="ENCOUNTER_CREATED",
            action="Created clinical encounter",
            actor=actor,
            patient_id=patient_id,
            encounter_id=encounter.id,
        )
        self.session.commit()
        self.session.refresh(encounter)
        return encounter

    def get(self, encounter_id: str, *, with_details: bool = True) -> ClinicalEncounter:
        encounter = self.encounters.get(encounter_id, with_details=with_details)
        if encounter is None:
            raise EntityNotFoundError("encounter", encounter_id)
        return encounter

    def update(
        self, encounter_id: str, payload: EncounterUpdate, *, actor: str = "kiosk-user"
    ) -> ClinicalEncounter:
        encounter = self.get(encounter_id, with_details=False)
        changes = payload.model_dump(exclude_unset=True)
        if changes.get("status") == EncounterStatus.COMPLETED and "completed_at" not in changes:
            changes["completed_at"] = datetime.now(timezone.utc)
        for field, value in changes.items():
            setattr(encounter, field, value)
        record_audit_event(
            self.session,
            event_type="ENCOUNTER_UPDATED",
            action="Updated clinical encounter",
            actor=actor,
            patient_id=encounter.patient_id,
            encounter_id=encounter.id,
            metadata={"changed_fields": sorted(changes)},
        )
        self.session.commit()
        return self.get(encounter_id)

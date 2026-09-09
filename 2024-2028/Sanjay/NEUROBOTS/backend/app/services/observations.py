from sqlalchemy.orm import Session

from app.core.exceptions import EntityNotFoundError
from app.db.models import LabResult, Symptom, VitalSigns
from app.repositories.clinical import EncounterRepository, ObservationRepository
from app.schemas.clinical import LabResultCreate, SymptomCreate, VitalSignsCreate
from app.services.audit import record_audit_event


class ObservationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.encounters = EncounterRepository(session)
        self.observations = ObservationRepository(session)

    def _encounter(self, encounter_id: str):
        encounter = self.encounters.get(encounter_id)
        if encounter is None:
            raise EntityNotFoundError("encounter", encounter_id)
        return encounter

    def add_symptom(
        self, encounter_id: str, payload: SymptomCreate, *, actor: str = "kiosk-user"
    ) -> Symptom:
        encounter = self._encounter(encounter_id)
        symptom = self.observations.add_symptom(
            Symptom(encounter_id=encounter_id, **payload.model_dump())
        )
        self._audit_observation(encounter.patient_id, encounter_id, symptom, actor)
        self.session.commit()
        self.session.refresh(symptom)
        return symptom

    def list_symptoms(self, encounter_id: str) -> list[Symptom]:
        self._encounter(encounter_id)
        return self.observations.list_symptoms(encounter_id)

    def add_vitals(
        self, encounter_id: str, payload: VitalSignsCreate, *, actor: str = "kiosk-user"
    ) -> VitalSigns:
        encounter = self._encounter(encounter_id)
        vitals = self.observations.add_vitals(
            VitalSigns(encounter_id=encounter_id, **payload.model_dump())
        )
        self._audit_observation(encounter.patient_id, encounter_id, vitals, actor)
        self.session.commit()
        self.session.refresh(vitals)
        return vitals

    def list_vitals(self, encounter_id: str) -> list[VitalSigns]:
        self._encounter(encounter_id)
        return self.observations.list_vitals(encounter_id)

    def add_lab(
        self, encounter_id: str, payload: LabResultCreate, *, actor: str = "kiosk-user"
    ) -> LabResult:
        encounter = self._encounter(encounter_id)
        lab = self.observations.add_lab(
            LabResult(encounter_id=encounter_id, **payload.model_dump())
        )
        self._audit_observation(encounter.patient_id, encounter_id, lab, actor)
        self.session.commit()
        self.session.refresh(lab)
        return lab

    def list_labs(self, encounter_id: str) -> list[LabResult]:
        self._encounter(encounter_id)
        return self.observations.list_labs(encounter_id)

    def _audit_observation(
        self, patient_id: str, encounter_id: str, observation, actor: str
    ) -> None:
        observation_type = type(observation).__name__.upper()
        record_audit_event(
            self.session,
            event_type=f"{observation_type}_CREATED",
            action=f"Recorded {type(observation).__name__}",
            actor=actor,
            patient_id=patient_id,
            encounter_id=encounter_id,
            metadata={"observation_id": observation.id, "source": observation.source.value},
        )

import random

from sqlalchemy.orm import Session

from app.core.enums import ObservationSource
from app.schemas.clinical import VitalSignsCreate
from app.services.observations import ObservationService


class VitalSignsSimulator:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.observations = ObservationService(session)

    def create_reading(self, encounter_id: str):
        existing_count = len(self.observations.list_vitals(encounter_id))
        randomizer = random.Random(f"{encounter_id}:{existing_count}")
        payload = VitalSignsCreate(
            heart_rate=round(randomizer.uniform(68, 110), 1),
            systolic_bp=round(randomizer.uniform(105, 155), 1),
            diastolic_bp=round(randomizer.uniform(65, 95), 1),
            spo2=round(randomizer.uniform(94, 100), 1),
            respiratory_rate=round(randomizer.uniform(12, 24), 1),
            temperature=round(randomizer.uniform(36.2, 37.6), 1),
            source=ObservationSource.SIMULATOR,
        )
        return self.observations.add_vitals(encounter_id, payload, actor="vital-simulator")

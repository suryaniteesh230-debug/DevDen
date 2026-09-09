from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import EncounterStatus, ObservationSource


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApiSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True, allow_inf_nan=False)


class PatientCreate(ApiSchema):
    external_patient_id: str = Field(min_length=1, max_length=64)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    gender: str = Field(min_length=1, max_length=50)
    phone_number: str | None = Field(default=None, max_length=30)


class PatientRead(PatientCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime


class EncounterCreate(ApiSchema):
    encounter_type: str = Field(min_length=1, max_length=80)
    chief_complaint: str = Field(min_length=1, max_length=2000)
    clinician_notes: str | None = Field(default=None, max_length=10000)
    status: EncounterStatus = EncounterStatus.ACTIVE
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class EncounterUpdate(ApiSchema):
    encounter_type: str | None = Field(default=None, min_length=1, max_length=80)
    chief_complaint: str | None = Field(default=None, min_length=1, max_length=2000)
    clinician_notes: str | None = Field(default=None, max_length=10000)
    status: EncounterStatus | None = None
    completed_at: datetime | None = None


class EncounterRead(ApiSchema):
    id: UUID
    patient_id: UUID
    encounter_type: str
    chief_complaint: str
    clinician_notes: str | None
    status: EncounterStatus
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SymptomCreate(ApiSchema):
    name: str = Field(min_length=1, max_length=120)
    severity: int | None = Field(default=None, ge=0, le=10)
    duration: str | None = Field(default=None, max_length=100)
    onset: datetime | None = None
    present: bool = True
    source: ObservationSource = ObservationSource.MANUAL


class SymptomRead(SymptomCreate):
    id: UUID
    encounter_id: UUID
    created_at: datetime


class VitalSignsCreate(ApiSchema):
    heart_rate: float | None = Field(default=None, gt=0, le=300)
    systolic_bp: float | None = Field(default=None, gt=0, le=300)
    diastolic_bp: float | None = Field(default=None, gt=0, le=250)
    spo2: float | None = Field(default=None, ge=0, le=100)
    respiratory_rate: float | None = Field(default=None, gt=0, le=100)
    temperature: float | None = Field(default=None, ge=20, le=50)
    measured_at: datetime = Field(default_factory=utc_now)
    source: ObservationSource = ObservationSource.MANUAL

    @model_validator(mode="after")
    def require_a_measurement(self) -> "VitalSignsCreate":
        measurement_fields = (
            self.heart_rate,
            self.systolic_bp,
            self.diastolic_bp,
            self.spo2,
            self.respiratory_rate,
            self.temperature,
        )
        if all(value is None for value in measurement_fields):
            raise ValueError("at least one vital-sign measurement is required")
        return self


class VitalSignsRead(VitalSignsCreate):
    id: UUID
    encounter_id: UUID


class LabResultCreate(ApiSchema):
    test_name: str = Field(min_length=1, max_length=120)
    value: float
    unit: str | None = Field(default=None, max_length=50)
    collected_at: datetime = Field(default_factory=utc_now)
    source: ObservationSource = ObservationSource.MANUAL
    reference_metadata: dict[str, Any] | None = None


class LabResultRead(LabResultCreate):
    id: UUID
    encounter_id: UUID


class EncounterDetail(EncounterRead):
    symptoms: list[SymptomRead]
    vital_signs: list[VitalSignsRead]
    lab_results: list[LabResultRead]


class PatientHistory(ApiSchema):
    patient: PatientRead
    encounters: list[EncounterDetail]

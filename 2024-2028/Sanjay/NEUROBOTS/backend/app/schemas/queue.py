from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import PriorityBand, QueueStatus


class QueueStatusUpdate(BaseModel):
    queue_status: QueueStatus


class QueuePatientDisplay(BaseModel):
    display_name: str
    age_years: int
    chief_complaint: str


class PendingQueueEntryRead(BaseModel):
    id: str
    patient_id: UUID
    encounter_id: UUID | None
    patient_display: QueuePatientDisplay
    intake_stage: str
    waiting_since: datetime
    waiting_duration_minutes: float


class QueueEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    encounter_id: UUID
    patient_id: UUID
    patient_display: QueuePatientDisplay
    queue_status: QueueStatus
    priority_score: float
    priority_band: PriorityBand
    rank: int | None
    waiting_since: datetime
    waiting_duration_minutes: float
    prototype_esi_level: int | None
    triage_severity: str
    cardiac_risk_probability: float | None
    cardiac_risk_model_version: str | None
    deterioration_status: str
    provisional: bool
    reason_codes: list[str]
    policy_name: str
    policy_version: str
    triage_assessment_id: UUID
    risk_prediction_id: UUID | None
    last_reassessment_at: datetime
    created_at: datetime
    updated_at: datetime


class QueueEntryDetail(QueueEntryRead):
    rule_trace: list[dict[str, Any]]
    calculation_count: int


def queue_entry_payload(
    entry: Any,
    *,
    rank: int | None,
    include_trace: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or datetime.now(timezone.utc)
    waiting_since = entry.waiting_since
    if waiting_since.tzinfo is None:
        waiting_since = waiting_since.replace(tzinfo=timezone.utc)
    waiting_minutes = max(0.0, (current_time - waiting_since).total_seconds() / 60)
    snapshot = entry.input_snapshot
    triage = snapshot.get("triage", {})
    cardiac = snapshot.get("cardiac_risk", {})
    encounter = entry.encounter
    patient = encounter.patient
    reference_date = encounter.started_at.date()
    birth_date: date = patient.date_of_birth
    age = reference_date.year - birth_date.year - (
        (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day)
    )
    value = {
        "id": entry.id,
        "encounter_id": entry.encounter_id,
        "patient_id": entry.patient_id,
        "patient_display": {
            "display_name": f"{patient.first_name} {patient.last_name}",
            "age_years": age,
            "chief_complaint": encounter.chief_complaint,
        },
        "queue_status": entry.queue_status,
        "priority_score": entry.priority_score,
        "priority_band": entry.priority_band,
        "rank": rank,
        "waiting_since": entry.waiting_since,
        "waiting_duration_minutes": round(waiting_minutes, 3),
        "prototype_esi_level": triage.get("prototype_esi_level"),
        "triage_severity": triage.get("severity_level"),
        "cardiac_risk_probability": cardiac.get("probability"),
        "cardiac_risk_model_version": cardiac.get("model_version"),
        "deterioration_status": entry.deterioration_status,
        "provisional": bool(triage.get("provisional")),
        "reason_codes": entry.reason_codes,
        "policy_name": entry.policy_name,
        "policy_version": entry.policy_version,
        "triage_assessment_id": entry.triage_assessment_id,
        "risk_prediction_id": entry.risk_prediction_id,
        "last_reassessment_at": entry.last_recalculated_at,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
    }
    if include_trace:
        value.update(
            rule_trace=entry.rule_trace,
            calculation_count=len(entry.calculations),
        )
    return value

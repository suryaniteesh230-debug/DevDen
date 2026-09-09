from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.enums import QueueStatus
from app.db.session import get_db
from app.schemas.queue import (
    PendingQueueEntryRead,
    QueueEntryDetail,
    QueueEntryRead,
    QueueStatusUpdate,
    queue_entry_payload,
)
from app.services.dynamic_queue import DynamicQueueService


router = APIRouter(prefix="/queue", tags=["queue"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[QueueEntryRead])
async def list_queue(
    session: DatabaseSession,
    status: QueueStatus = QueueStatus.WAITING,
):
    service = DynamicQueueService(session)
    entries = service.list(status=status)
    return [
        queue_entry_payload(
            entry,
            rank=index if status == QueueStatus.WAITING else None,
        )
        for index, entry in enumerate(entries, start=1)
    ]


@router.get("/pending", response_model=list[PendingQueueEntryRead])
async def list_pending_queue(session: DatabaseSession):
    now = datetime.now(timezone.utc)
    pending = DynamicQueueService(session).list_pending_intake()
    result = []
    for patient, encounter in pending:
        waiting_since = encounter.started_at if encounter else patient.created_at
        if waiting_since.tzinfo is None:
            waiting_since = waiting_since.replace(tzinfo=timezone.utc)
        reference_date = (encounter.started_at if encounter else now).date()
        age = reference_date.year - patient.date_of_birth.year - (
            (reference_date.month, reference_date.day)
            < (patient.date_of_birth.month, patient.date_of_birth.day)
        )
        result.append(
            {
                "id": f"pending:{encounter.id if encounter else patient.id}",
                "patient_id": patient.id,
                "encounter_id": encounter.id if encounter else None,
                "patient_display": {
                    "display_name": f"{patient.first_name} {patient.last_name}",
                    "age_years": age,
                    "chief_complaint": (
                        encounter.chief_complaint
                        if encounter
                        else "Chief complaint not recorded"
                    ),
                },
                "intake_stage": "TRIAGE" if encounter else "REGISTRATION",
                "waiting_since": waiting_since,
                "waiting_duration_minutes": round(
                    max(0.0, (now - waiting_since).total_seconds() / 60), 3
                ),
            }
        )
    return result


@router.get("/{queue_entry_id}", response_model=QueueEntryDetail)
async def get_queue_entry(queue_entry_id: str, session: DatabaseSession):
    service = DynamicQueueService(session)
    entry = service.get(queue_entry_id)
    return queue_entry_payload(
        entry,
        rank=service.rank(entry.id),
        include_trace=True,
    )


@router.patch("/{queue_entry_id}", response_model=QueueEntryRead)
async def update_queue_status(
    queue_entry_id: str,
    payload: QueueStatusUpdate,
    session: DatabaseSession,
):
    service = DynamicQueueService(session)
    entry = service.change_status(queue_entry_id, payload.queue_status)
    return queue_entry_payload(entry, rank=service.rank(entry.id))

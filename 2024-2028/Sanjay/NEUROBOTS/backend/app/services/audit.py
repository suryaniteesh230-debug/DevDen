from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditEvent
from app.repositories.clinical import AuditRepository


def record_audit_event(
    session: Session,
    *,
    event_type: str,
    action: str,
    actor: str = "kiosk-user",
    patient_id: str | None = None,
    encounter_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    event = AuditEvent(
        event_type=event_type,
        action=action,
        actor=actor,
        patient_id=patient_id,
        encounter_id=encounter_id,
        event_metadata=metadata,
    )
    return AuditRepository(session).add(event)

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import PriorityBand, QueueStatus
from app.core.exceptions import ClinicalApiError, EntityNotFoundError
from app.db.models import QueueEntry, QueuePriorityCalculation
from app.priority.policy import DynamicPriorityPolicy
from app.repositories.clinical import (
    EncounterRepository,
    QueueEntryRepository,
    QueuePriorityCalculationRepository,
)
from app.services.audit import record_audit_event


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class DynamicQueueService:
    """Persistent queue projection independent of FastAPI and LangGraph."""

    def __init__(
        self,
        session: Session,
        *,
        policy: DynamicPriorityPolicy | None = None,
    ) -> None:
        self.session = session
        self.policy = policy or DynamicPriorityPolicy()
        self.entries = QueueEntryRepository(session)
        self.calculations = QueuePriorityCalculationRepository(session)
        self.encounters = EncounterRepository(session)

    def recalculate(
        self,
        *,
        encounter_id: str,
        patient_id: str,
        triage: dict[str, Any],
        cardiac_risk: dict[str, Any] | None,
        vital_history: list[dict[str, Any]] | None,
        waiting_since: datetime | str | None = None,
        now: datetime | None = None,
        actor: str = "priority-agent",
    ) -> dict[str, Any]:
        encounter = self.encounters.get(encounter_id)
        if encounter is None:
            raise EntityNotFoundError("encounter", encounter_id)
        if encounter.patient_id != patient_id:
            raise ValueError("Queue patient does not own the encounter")

        existing = self.entries.get_for_encounter(encounter_id)
        waiting_value = waiting_since or (
            existing.waiting_since if existing else encounter.started_at
        )
        effective_waiting_since = _datetime(waiting_value)
        calculated_at = now or datetime.now(timezone.utc)
        result = self.policy.calculate(
            triage=triage,
            cardiac_risk=cardiac_risk,
            vital_history=vital_history,
            waiting_since=effective_waiting_since,
            now=calculated_at,
        )
        if result["status"] != "SUCCESS":
            return result

        previous_snapshot: dict[str, Any] | None = None
        if existing is None:
            entry = self.entries.add(
                QueueEntry(
                    encounter_id=encounter_id,
                    patient_id=patient_id,
                    queue_status=QueueStatus.WAITING,
                    waiting_since=effective_waiting_since,
                    priority_score=result["priority_score"],
                    priority_band=PriorityBand(result["priority_band"]),
                    policy_name=result["policy_name"],
                    policy_version=result["policy_version"],
                    triage_assessment_id=triage["assessment_id"],
                    risk_prediction_id=(cardiac_risk or {}).get("prediction_id"),
                    reason_codes=result["reason_codes"],
                    rule_trace=result["rule_trace"],
                    input_snapshot=result["input_snapshot"],
                    deterioration_status=result["deterioration_status"],
                    last_recalculated_at=calculated_at,
                )
            )
            event_type = "QUEUE_ENTRY_CREATED"
            action = "Created dynamic patient queue entry"
        else:
            entry = existing
            previous_snapshot = {
                "priority_score": entry.priority_score,
                "priority_band": entry.priority_band.value,
                "triage_assessment_id": entry.triage_assessment_id,
                "risk_prediction_id": entry.risk_prediction_id,
                "reason_codes": entry.reason_codes,
                "deterioration_status": entry.deterioration_status,
                "last_recalculated_at": entry.last_recalculated_at.isoformat(),
            }
            entry.priority_score = result["priority_score"]
            entry.priority_band = PriorityBand(result["priority_band"])
            entry.policy_name = result["policy_name"]
            entry.policy_version = result["policy_version"]
            entry.triage_assessment_id = triage["assessment_id"]
            entry.risk_prediction_id = (cardiac_risk or {}).get("prediction_id")
            entry.reason_codes = result["reason_codes"]
            entry.rule_trace = result["rule_trace"]
            entry.input_snapshot = result["input_snapshot"]
            entry.deterioration_status = result["deterioration_status"]
            entry.last_recalculated_at = calculated_at
            event_type = "QUEUE_PRIORITY_RECALCULATED"
            action = "Recalculated dynamic patient queue priority"
            self.session.flush()

        calculation = self.calculations.add(
            QueuePriorityCalculation(
                queue_entry_id=entry.id,
                triage_assessment_id=triage["assessment_id"],
                risk_prediction_id=(cardiac_risk or {}).get("prediction_id"),
                policy_name=result["policy_name"],
                policy_version=result["policy_version"],
                priority_score=result["priority_score"],
                priority_band=PriorityBand(result["priority_band"]),
                reason_codes=result["reason_codes"],
                rule_trace=result["rule_trace"],
                input_snapshot=result["input_snapshot"],
                deterioration_status=result["deterioration_status"],
                calculated_at=calculated_at,
            )
        )
        record_audit_event(
            self.session,
            event_type=event_type,
            action=action,
            actor=actor,
            patient_id=patient_id,
            encounter_id=encounter_id,
            metadata={
                "queue_entry_id": entry.id,
                "calculation_id": calculation.id,
                "policy_name": result["policy_name"],
                "policy_version": result["policy_version"],
                "priority_score": result["priority_score"],
                "priority_band": result["priority_band"],
                "reason_codes": result["reason_codes"],
                "previous": previous_snapshot,
            },
        )
        self.session.commit()
        self.session.refresh(entry)
        return {
            **result,
            "queue_entry_id": entry.id,
            "calculation_id": calculation.id,
            "queue_status": entry.queue_status.value,
            "triage_assessment_id": entry.triage_assessment_id,
            "risk_prediction_id": entry.risk_prediction_id,
            "waiting_since": _aware(entry.waiting_since).isoformat(),
            "last_recalculated_at": _aware(entry.last_recalculated_at).isoformat(),
            "rank": self.rank(entry.id),
        }

    def rank(self, queue_entry_id: str) -> int | None:
        waiting = self.entries.list(status=QueueStatus.WAITING)
        return next(
            (index for index, item in enumerate(waiting, start=1) if item.id == queue_entry_id),
            None,
        )

    def get(self, queue_entry_id: str) -> QueueEntry:
        entry = self.entries.get(queue_entry_id)
        if entry is None:
            raise EntityNotFoundError("queue entry", queue_entry_id)
        return entry

    def list(self, *, status: QueueStatus = QueueStatus.WAITING) -> list[QueueEntry]:
        return self.entries.list(status=status)

    def list_pending_intake(self):
        return self.entries.list_pending_intake()

    def change_status(
        self,
        queue_entry_id: str,
        status: QueueStatus,
        *,
        actor: str = "kiosk-user",
    ) -> QueueEntry:
        entry = self.get(queue_entry_id)
        previous = entry.queue_status
        if previous == status:
            return entry
        allowed = {
            QueueStatus.WAITING: {
                QueueStatus.CALLED,
                QueueStatus.IN_ASSESSMENT,
                QueueStatus.COMPLETED,
                QueueStatus.REMOVED,
            },
            QueueStatus.CALLED: {
                QueueStatus.WAITING,
                QueueStatus.IN_ASSESSMENT,
                QueueStatus.COMPLETED,
                QueueStatus.REMOVED,
            },
            QueueStatus.IN_ASSESSMENT: {
                QueueStatus.WAITING,
                QueueStatus.COMPLETED,
                QueueStatus.REMOVED,
            },
            QueueStatus.COMPLETED: set(),
            QueueStatus.REMOVED: set(),
        }
        if status not in allowed[previous]:
            raise ClinicalApiError(
                "INVALID_QUEUE_TRANSITION",
                f"Queue status cannot change from {previous.value} to {status.value}",
                409,
            )
        entry.queue_status = status
        record_audit_event(
            self.session,
            event_type="QUEUE_STATUS_CHANGED",
            action="Changed operational patient queue status",
            actor=actor,
            patient_id=entry.patient_id,
            encounter_id=entry.encounter_id,
            metadata={
                "queue_entry_id": entry.id,
                "previous_status": previous.value,
                "new_status": status.value,
            },
        )
        self.session.commit()
        self.session.refresh(entry)
        return entry

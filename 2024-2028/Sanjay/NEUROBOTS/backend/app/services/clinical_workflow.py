from contextlib import nullcontext
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import EntityNotFoundError
from app.db.session import SessionLocal
from app.services.audit import record_audit_event
from app.services.encounters import EncounterService
from app.services.patients import PatientService
from app.workflows.clinical_graph import build_clinical_graph
from app.workflows.clinical_state import ClinicalState, create_initial_clinical_state


def _audit_workflow(
    session: Session,
    state: ClinicalState,
    *,
    event_type: str,
    action: str,
    status: str,
) -> None:
    patient_reference: str | None = None
    encounter_reference: str | None = None
    try:
        patient = PatientService(session).get(state["patient_id"])
        encounter = EncounterService(session).get(state["encounter_id"], with_details=False)
        if encounter.patient_id == patient.id:
            patient_reference = patient.id
            encounter_reference = encounter.id
    except EntityNotFoundError:
        pass

    record_audit_event(
        session,
        event_type=event_type,
        action=action,
        actor="clinical-workflow",
        patient_id=patient_reference,
        encounter_id=encounter_reference,
        metadata={
            "workflow_id": state["workflow_id"],
            "requested_patient_id": state["patient_id"],
            "requested_encounter_id": state["encounter_id"],
            "status": status,
            "agent_count": len(state.get("agent_trace", [])),
        },
    )
    session.commit()


def _safe_audit(
    session: Session,
    state: ClinicalState,
    *,
    event_type: str,
    action: str,
    status: str,
) -> None:
    try:
        _audit_workflow(
            session,
            state,
            event_type=event_type,
            action=action,
            status=status,
        )
    except Exception as exception:
        session.rollback()
        state["warnings"] = [
            *state.get("warnings", []),
            f"Workflow audit could not be recorded: {type(exception).__name__}: {exception}",
        ]


def _run_with_session(session: Session, patient_id: str, encounter_id: str) -> ClinicalState:
    state = create_initial_clinical_state(patient_id, encounter_id)
    _safe_audit(
        session,
        state,
        event_type="CLINICAL_WORKFLOW_STARTED",
        action="Started Phase 1 clinical assessment workflow",
        status="STARTED",
    )

    try:
        result: dict[str, Any] = build_clinical_graph(session).invoke(
            state, config={"recursion_limit": 32}
        )
        final_state = ClinicalState(**result)
    except Exception as exception:
        final_state = state
        final_state["workflow_halted"] = True
        final_state["workflow_status"] = "FAILED"
        final_state["next_action"] = "FINISH"
        final_state["errors"] = [
            *final_state.get("errors", []),
            f"Workflow execution failed safely: {type(exception).__name__}: {exception}",
        ]

    failed = (
        final_state.get("workflow_halted", False)
        or final_state.get("workflow_status") == "FAILED"
    )
    _safe_audit(
        session,
        final_state,
        event_type="CLINICAL_WORKFLOW_FAILED" if failed else "CLINICAL_WORKFLOW_COMPLETED",
        action=(
            "Failed Phase 1 clinical assessment workflow"
            if failed
            else "Completed Phase 1 clinical assessment workflow"
        ),
        status="FAILED" if failed else "COMPLETED",
    )
    return final_state


def run_clinical_assessment(
    patient_id: str,
    encounter_id: str,
    *,
    session: Session | None = None,
) -> ClinicalState:
    """Run the workflow from Python, optionally inside an existing DB session."""

    session_context = nullcontext(session) if session is not None else SessionLocal()
    with session_context as active_session:
        return _run_with_session(active_session, patient_id, encounter_id)

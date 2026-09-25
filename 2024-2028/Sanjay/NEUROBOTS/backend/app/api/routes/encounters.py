from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.clinical import (
    EncounterDetail,
    EncounterUpdate,
    LabResultCreate,
    LabResultRead,
    SymptomCreate,
    SymptomRead,
    VitalSignsCreate,
    VitalSignsRead,
)
from app.schemas.workflow import ClinicalWorkflowResponse
from app.services.clinical_workflow import run_clinical_assessment
from app.services.encounters import EncounterService
from app.services.observations import ObservationService
from app.services.simulator import VitalSignsSimulator


router = APIRouter(prefix="/encounters", tags=["encounters"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/{encounter_id}", response_model=EncounterDetail)
async def get_encounter(encounter_id: str, session: DatabaseSession):
    return EncounterService(session).get(encounter_id)


@router.patch("/{encounter_id}", response_model=EncounterDetail)
async def update_encounter(
    encounter_id: str, payload: EncounterUpdate, session: DatabaseSession
):
    return EncounterService(session).update(encounter_id, payload)


@router.post(
    "/{encounter_id}/symptoms",
    response_model=SymptomRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_symptom(encounter_id: str, payload: SymptomCreate, session: DatabaseSession):
    return ObservationService(session).add_symptom(encounter_id, payload)


@router.get("/{encounter_id}/symptoms", response_model=list[SymptomRead])
async def list_symptoms(encounter_id: str, session: DatabaseSession):
    return ObservationService(session).list_symptoms(encounter_id)


@router.post(
    "/{encounter_id}/vitals",
    response_model=VitalSignsRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_vitals(encounter_id: str, payload: VitalSignsCreate, session: DatabaseSession):
    return ObservationService(session).add_vitals(encounter_id, payload)


@router.get("/{encounter_id}/vitals", response_model=list[VitalSignsRead])
async def list_vitals(encounter_id: str, session: DatabaseSession):
    return ObservationService(session).list_vitals(encounter_id)


@router.post(
    "/{encounter_id}/simulate-vitals",
    response_model=VitalSignsRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def simulate_vitals(encounter_id: str, session: DatabaseSession):
    return VitalSignsSimulator(session).create_reading(encounter_id)


@router.post(
    "/{encounter_id}/labs",
    response_model=LabResultRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_lab(encounter_id: str, payload: LabResultCreate, session: DatabaseSession):
    return ObservationService(session).add_lab(encounter_id, payload)


@router.get("/{encounter_id}/labs", response_model=list[LabResultRead])
async def list_labs(encounter_id: str, session: DatabaseSession):
    return ObservationService(session).list_labs(encounter_id)


@router.post(
    "/{encounter_id}/workflow",
    response_model=ClinicalWorkflowResponse,
    summary="Run the Phase 1 multi-agent clinical workflow",
)
@router.post(
    "/{encounter_id}/assessment-workflow",
    response_model=ClinicalWorkflowResponse,
    include_in_schema=False,
)
async def run_assessment_workflow(encounter_id: str, session: DatabaseSession):
    encounter = EncounterService(session).get(encounter_id, with_details=False)
    return run_clinical_assessment(encounter.patient_id, encounter_id, session=session)

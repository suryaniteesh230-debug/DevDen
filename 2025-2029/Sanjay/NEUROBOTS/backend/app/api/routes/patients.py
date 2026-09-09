from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.clinical import (
    EncounterCreate,
    EncounterRead,
    PatientCreate,
    PatientHistory,
    PatientRead,
)
from app.services.encounters import EncounterService
from app.services.patients import PatientService


router = APIRouter(prefix="/patients", tags=["patients"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=PatientRead, status_code=status.HTTP_201_CREATED)
async def create_patient(payload: PatientCreate, session: DatabaseSession):
    return PatientService(session).create(payload)


@router.get("", response_model=list[PatientRead])
async def search_patients(
    session: DatabaseSession,
    external_patient_id: str | None = Query(default=None, min_length=1, max_length=64),
    name: str | None = Query(default=None, min_length=1, max_length=200),
    limit: int = Query(default=25, ge=1, le=100),
):
    return PatientService(session).search(external_patient_id, name, limit)


@router.get("/{patient_id}", response_model=PatientRead)
async def get_patient(patient_id: str, session: DatabaseSession):
    return PatientService(session).get(patient_id)


@router.get("/{patient_id}/history", response_model=PatientHistory)
async def get_patient_history(patient_id: str, session: DatabaseSession):
    patient, encounters = PatientService(session).history(patient_id)
    return PatientHistory(patient=patient, encounters=encounters)


@router.post(
    "/{patient_id}/encounters",
    response_model=EncounterRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_encounter(patient_id: str, payload: EncounterCreate, session: DatabaseSession):
    return EncounterService(session).create(patient_id, payload)

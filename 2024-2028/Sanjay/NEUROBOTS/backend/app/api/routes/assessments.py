from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.assessment import AssessmentHistoryRead, LatestAssessmentRead
from app.services.assessment_history import AssessmentHistoryService


router = APIRouter(prefix="/encounters", tags=["assessments"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.get("/{encounter_id}/assessment", response_model=LatestAssessmentRead)
async def get_latest_assessment(encounter_id: str, session: DatabaseSession):
    return AssessmentHistoryService(session).latest(encounter_id)


@router.get("/{encounter_id}/assessment-history", response_model=AssessmentHistoryRead)
async def get_assessment_history(encounter_id: str, session: DatabaseSession):
    return AssessmentHistoryService(session).history(encounter_id)

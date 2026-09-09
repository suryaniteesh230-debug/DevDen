from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import (
    CurrentStaffUser,
    authenticate_staff,
    create_access_token,
)
from app.db.session import get_db
from app.schemas.auth import StaffLogin, StaffTokenResponse, StaffUserRead


router = APIRouter(prefix="/auth", tags=["authentication"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post("/login", response_model=StaffTokenResponse)
async def login(payload: StaffLogin, session: DatabaseSession) -> StaffTokenResponse:
    staff_user = authenticate_staff(session, payload.email, payload.password)
    access_token, expires_in = create_access_token(staff_user)
    return StaffTokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        staff=staff_user,
    )


@router.get("/me", response_model=StaffUserRead)
async def current_staff_user(staff_user: CurrentStaffUser) -> StaffUserRead:
    return StaffUserRead.model_validate(staff_user)

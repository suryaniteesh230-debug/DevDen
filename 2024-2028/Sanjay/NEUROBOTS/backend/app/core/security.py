import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ClinicalApiError
from app.db.models import StaffUser
from app.db.session import get_db


JWT_ALGORITHM = "HS256"
JWT_ISSUER = "nextcare"
JWT_AUDIENCE = "nextcare-medical-staff"
password_hash = PasswordHash.recommended()
_DUMMY_PASSWORD_HASH = password_hash.hash("nextcare-invalid-credential-placeholder")
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return password_hash.verify(password, encoded_hash)
    except (PwdlibError, TypeError, ValueError):
        return False


@lru_cache
def _secret_key() -> str:
    settings = get_settings()
    secret = settings.auth_secret_key.get_secret_value()
    if not secret and settings.environment.lower() == "development":
        return secrets.token_urlsafe(48)
    if len(secret) < 32:
        raise ClinicalApiError(
            "AUTH_NOT_CONFIGURED",
            "Staff authentication is not configured",
            503,
        )
    return secret


def authenticate_staff(session: Session, email: str, password: str) -> StaffUser:
    staff_user = session.scalar(select(StaffUser).where(StaffUser.email == email))
    encoded_hash = staff_user.password_hash if staff_user is not None else _DUMMY_PASSWORD_HASH
    password_is_valid = verify_password(password, encoded_hash)
    if staff_user is None or not password_is_valid or not staff_user.is_active:
        raise ClinicalApiError("INVALID_CREDENTIALS", "Invalid credentials", 401)
    return staff_user


def create_access_token(staff_user: StaffUser) -> tuple[str, int]:
    settings = get_settings()
    expires_in = settings.auth_access_token_expire_minutes * 60
    issued_at = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": staff_user.id,
            "iat": issued_at,
            "exp": issued_at + timedelta(seconds=expires_in),
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "type": "access",
        },
        _secret_key(),
        algorithm=JWT_ALGORITHM,
    )
    return token, expires_in


def _decode_staff_id(token: str) -> str:
    try:
        payload = jwt.decode(
            token,
            _secret_key(),
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"require": ["sub", "iat", "exp", "type"]},
        )
    except PyJWTError as exception:
        raise ClinicalApiError(
            "AUTHENTICATION_REQUIRED",
            "Valid staff authentication is required",
            401,
        ) from exception
    if payload.get("type") != "access" or not isinstance(payload.get("sub"), str):
        raise ClinicalApiError(
            "AUTHENTICATION_REQUIRED",
            "Valid staff authentication is required",
            401,
        )
    return payload["sub"]


async def get_current_staff_user(
    session: Annotated[Session, Depends(get_db)],
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
) -> StaffUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ClinicalApiError(
            "AUTHENTICATION_REQUIRED",
            "Valid staff authentication is required",
            401,
        )
    staff_user = session.get(StaffUser, _decode_staff_id(credentials.credentials))
    if staff_user is None or not staff_user.is_active:
        raise ClinicalApiError(
            "AUTHENTICATION_REQUIRED",
            "Valid staff authentication is required",
            401,
        )
    return staff_user


require_staff_user = get_current_staff_user
CurrentStaffUser = Annotated[StaffUser, Depends(get_current_staff_user)]

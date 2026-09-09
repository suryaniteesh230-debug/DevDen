from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import ClinicalApiError, DuplicateEntityError, EntityNotFoundError
from app.db.base import Base
from app.db.session import engine
from app.db import models  # noqa: F401


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Offline-first clinical data API for a decision-support prototype. "
        "It does not provide autonomous diagnosis."
    ),
)


@app.on_event("startup")
async def ensure_database_schema() -> None:
    try:
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError as exception:
        raise RuntimeError("Failed to initialize the database schema") from exception


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "X-Filename"],
)


def error_response(
    status_code: int,
    code: str,
    detail: str,
    *,
    issues: list[dict[str, object]] | None = None,
) -> JSONResponse:
    error: dict[str, object] = {"code": code, "detail": detail}
    if issues:
        error["issues"] = issues
    return JSONResponse(status_code=status_code, content={"error": error})


@app.exception_handler(EntityNotFoundError)
async def handle_not_found(_request: Request, exception: EntityNotFoundError) -> JSONResponse:
    return error_response(404, "ENTITY_NOT_FOUND", str(exception))


@app.exception_handler(DuplicateEntityError)
async def handle_duplicate(_request: Request, exception: DuplicateEntityError) -> JSONResponse:
    return error_response(409, "DUPLICATE_ENTITY", str(exception))


@app.exception_handler(ClinicalApiError)
async def handle_clinical_api_error(
    _request: Request, exception: ClinicalApiError
) -> JSONResponse:
    return error_response(exception.status_code, exception.code, exception.detail)


@app.exception_handler(RequestValidationError)
async def handle_request_validation(
    _request: Request, exception: RequestValidationError
) -> JSONResponse:
    issues = [
        {
            "location": [str(part) for part in error["loc"]],
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exception.errors()
    ]
    return error_response(422, "INVALID_REQUEST", "Request validation failed", issues=issues)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "neurobots-clinical-api",
        "environment": settings.environment,
    }


app.include_router(api_router)

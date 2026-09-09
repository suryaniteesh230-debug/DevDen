from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ClinicalApiError
from app.db.session import get_db
from app.multimodal.ocr import OCRService, TesseractOCRService
from app.schemas.multimodal import ClinicalDocumentRead
from app.services.document_ingestion import DocumentIngestionService


router = APIRouter(tags=["multimodal"])
DatabaseSession = Annotated[Session, Depends(get_db)]


async def get_ocr_service() -> OCRService:
    return TesseractOCRService()


async def _bounded_body(request: Request) -> bytes:
    maximum = get_settings().document_upload_max_bytes
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > maximum:
                raise ClinicalApiError(
                    "DOCUMENT_TOO_LARGE", f"Document uploads are limited to {maximum} bytes", 413
                )
        except ValueError as exception:
            raise ClinicalApiError("INVALID_CONTENT_LENGTH", "Invalid Content-Length header", 400) from exception
    content = await request.body()
    size = len(content)
    if size > maximum:
        raise ClinicalApiError(
            "DOCUMENT_TOO_LARGE", f"Document uploads are limited to {maximum} bytes", 413
        )
    if size == 0:
        raise ClinicalApiError("EMPTY_DOCUMENT", "Document upload is empty", 422)
    return content


@router.post(
    "/encounters/{encounter_id}/documents",
    response_model=ClinicalDocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and process a clinical document with local OCR",
)
async def ingest_document(
    encounter_id: str,
    request: Request,
    session: DatabaseSession,
    ocr_service: Annotated[OCRService, Depends(get_ocr_service)],
    x_filename: Annotated[str, Header(min_length=1, max_length=255)] = "clinical-document",
):
    content = await _bounded_body(request)
    content_type = request.headers.get("content-type", "application/octet-stream")
    return DocumentIngestionService(session, ocr_service=ocr_service).ingest(
        encounter_id=encounter_id,
        content=content,
        content_type=content_type,
        filename=x_filename,
    )


@router.get(
    "/encounters/{encounter_id}/documents",
    response_model=list[ClinicalDocumentRead],
)
async def list_documents(encounter_id: str, session: DatabaseSession):
    return DocumentIngestionService(session).list(encounter_id)


@router.get("/documents/{document_id}", response_model=ClinicalDocumentRead)
async def get_document(document_id: str, session: DatabaseSession):
    return DocumentIngestionService(session).get(document_id)

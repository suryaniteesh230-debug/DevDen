from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ClinicalApiError
from app.db.session import get_db
from app.multimodal.speech import SpeechService, get_speech_service
from app.schemas.speech import SpeechTranscriptionRead
from app.services.speech_ingestion import SpeechIngestionService


router = APIRouter(tags=["multimodal"])
DatabaseSession = Annotated[Session, Depends(get_db)]


async def _bounded_audio(request: Request) -> bytes:
    maximum = get_settings().speech_upload_max_bytes
    declared = request.headers.get("content-length")
    if declared:
        try:
            if int(declared) > maximum:
                raise ClinicalApiError(
                    "AUDIO_TOO_LARGE", f"Audio uploads are limited to {maximum} bytes", 413
                )
        except ValueError as exception:
            raise ClinicalApiError("INVALID_CONTENT_LENGTH", "Invalid Content-Length header", 400) from exception
    content = await request.body()
    if not content:
        raise ClinicalApiError("EMPTY_AUDIO", "Audio upload is empty", 422)
    if len(content) > maximum:
        raise ClinicalApiError(
            "AUDIO_TOO_LARGE", f"Audio uploads are limited to {maximum} bytes", 413
        )
    return content


@router.post(
    "/encounters/{encounter_id}/speech",
    response_model=SpeechTranscriptionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload English clinical speech for transcription and symptom extraction",
)
async def ingest_speech(
    encounter_id: str,
    request: Request,
    session: DatabaseSession,
    speech_service: Annotated[SpeechService, Depends(get_speech_service)],
    x_filename: Annotated[str, Header(min_length=1, max_length=255)] = "clinical-audio.wav",
):
    content = await _bounded_audio(request)
    return SpeechIngestionService(session, speech_service=speech_service).ingest(
        encounter_id=encounter_id,
        content=content,
        content_type=request.headers.get("content-type", "application/octet-stream"),
        filename=x_filename,
    )


@router.get(
    "/encounters/{encounter_id}/speech",
    response_model=list[SpeechTranscriptionRead],
)
async def list_speech(encounter_id: str, session: DatabaseSession):
    return SpeechIngestionService(session).list(encounter_id)


@router.get("/speech/{transcription_id}", response_model=SpeechTranscriptionRead)
async def get_speech(transcription_id: str, session: DatabaseSession):
    return SpeechIngestionService(session).get(transcription_id)

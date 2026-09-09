from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import ObservationSource


class SpeechTranscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    encounter_id: UUID
    original_filename: str
    safe_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    source: ObservationSource
    processing_status: str
    transcript: str
    provider: str
    model: str
    language: str
    confidence_metadata: dict[str, Any]
    extracted_symptoms: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    symptom_ids: list[UUID]
    transcription_latency_ms: float
    processed_at: datetime
    created_at: datetime

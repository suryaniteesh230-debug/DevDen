from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import ObservationSource


class ClinicalDocumentRead(BaseModel):
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
    ocr_text: str
    ocr_engine: str
    ocr_engine_version: str
    ocr_confidence: float | None
    extracted_fields: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    lab_result_ids: list[UUID]
    page_count: int
    processed_at: datetime
    created_at: datetime

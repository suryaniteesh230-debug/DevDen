from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import ObservationSource
from app.core.exceptions import ClinicalApiError, EntityNotFoundError
from app.db.models import ClinicalDocument, LabResult
from app.multimodal.ocr import OCRService, TesseractOCRService
from app.multimodal.parser import ClinicalDocumentParser
from app.repositories.clinical import (
    ClinicalDocumentRepository,
    EncounterRepository,
    ObservationRepository,
)
from app.services.audit import record_audit_event


def safe_filename(value: str) -> str:
    basename = Path(value.replace("\\", "/")).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", basename).strip("._")
    return (cleaned or "clinical-document")[:255]


def normalized_lab_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


class DocumentIngestionService:
    """Coordinates OCR, conservative parsing, and one transactional persistence path."""

    def __init__(
        self,
        session: Session,
        *,
        ocr_service: OCRService | None = None,
        parser: ClinicalDocumentParser | None = None,
    ) -> None:
        self.session = session
        self.ocr_service = ocr_service or TesseractOCRService()
        self.parser = parser or ClinicalDocumentParser()
        self.encounters = EncounterRepository(session)
        self.documents = ClinicalDocumentRepository(session)
        self.observations = ObservationRepository(session)

    def ingest(
        self,
        *,
        encounter_id: str,
        content: bytes,
        content_type: str,
        filename: str,
        actor: str = "kiosk-user",
    ) -> ClinicalDocument:
        encounter = self.encounters.get(encounter_id)
        if encounter is None:
            raise EntityNotFoundError("encounter", encounter_id)

        result = self.ocr_service.extract(content, content_type)
        parsed = self.parser.parse(result.text)
        existing_labs = self.observations.list_labs(encounter_id)
        conflicts = self._conflicts(parsed, existing_labs)
        document = self.documents.add(
            ClinicalDocument(
                encounter_id=encounter_id,
                original_filename=filename[:255],
                safe_filename=safe_filename(filename),
                content_type=content_type.split(";", 1)[0].strip().casefold(),
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                source=ObservationSource.OCR,
                processing_status="COMPLETED",
                ocr_text=result.text,
                ocr_engine=result.engine,
                ocr_engine_version=result.engine_version,
                ocr_confidence=result.confidence,
                extracted_fields=[item.as_dict() for item in parsed],
                conflicts=conflicts,
                lab_result_ids=[],
                page_count=result.page_count,
            )
        )
        lab_ids: list[str] = []
        for item in parsed:
            lab = self.observations.add_lab(
                LabResult(
                    encounter_id=encounter_id,
                    test_name=item.test_name,
                    value=item.value,
                    unit=item.unit,
                    source=ObservationSource.OCR,
                    reference_metadata={
                        "document_id": document.id,
                        "ocr_engine": result.engine,
                        "ocr_engine_version": result.engine_version,
                        "ocr_confidence": result.confidence,
                        "parser_name": self.parser.parser_name,
                        "parser_version": self.parser.parser_version,
                        "extraction_confidence": item.extraction_confidence,
                        "source_text": item.source_text,
                    },
                )
            )
            lab_ids.append(lab.id)
        document.lab_result_ids = lab_ids
        record_audit_event(
            self.session,
            event_type="CLINICAL_DOCUMENT_PROCESSED",
            action="Processed clinical document with local OCR",
            actor=actor,
            patient_id=encounter.patient_id,
            encounter_id=encounter_id,
            metadata={
                "document_id": document.id,
                "sha256": document.sha256,
                "ocr_engine": result.engine,
                "ocr_engine_version": result.engine_version,
                "extracted_field_count": len(parsed),
                "conflict_count": len(conflicts),
            },
        )
        self.session.commit()
        self.session.refresh(document)
        return document

    def get(self, document_id: str) -> ClinicalDocument:
        document = self.documents.get(document_id)
        if document is None:
            raise EntityNotFoundError("clinical document", document_id)
        return document

    def list(self, encounter_id: str) -> list[ClinicalDocument]:
        if self.encounters.get(encounter_id) is None:
            raise EntityNotFoundError("encounter", encounter_id)
        return self.documents.list_for_encounter(encounter_id)

    @staticmethod
    def _conflicts(parsed: list[Any], existing_labs: list[LabResult]) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        by_name: dict[str, list[LabResult]] = {}
        for lab in existing_labs:
            by_name.setdefault(normalized_lab_name(lab.test_name), []).append(lab)
        for item in parsed:
            for existing in by_name.get(normalized_lab_name(item.test_name), []):
                if existing.value == item.value and existing.unit == item.unit:
                    continue
                conflicts.append(
                    {
                        "field_type": "LAB_RESULT",
                        "test_name": item.test_name,
                        "existing_observation_id": existing.id,
                        "existing_source": existing.source.value,
                        "existing_value": existing.value,
                        "existing_unit": existing.unit,
                        "ocr_value": item.value,
                        "ocr_unit": item.unit,
                        "resolution": "PRESERVED_BOTH_REVIEW_REQUIRED",
                    }
                )
        return conflicts

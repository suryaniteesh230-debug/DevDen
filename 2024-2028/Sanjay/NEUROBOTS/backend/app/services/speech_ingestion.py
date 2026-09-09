from __future__ import annotations

import hashlib
import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import ObservationSource
from app.core.exceptions import EntityNotFoundError
from app.db.models import SpeechTranscription, Symptom
from app.multimodal.clinical_text import ClinicalTextExtractor
from app.multimodal.speech import SpeechService, build_speech_service, validate_audio_signature
from app.repositories.clinical import (
    EncounterRepository,
    ObservationRepository,
    SpeechTranscriptionRepository,
)
from app.services.audit import record_audit_event
from app.services.document_ingestion import safe_filename


def normalized_symptom_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


class SpeechIngestionService:
    def __init__(
        self,
        session: Session,
        *,
        speech_service: SpeechService | None = None,
        extractor: ClinicalTextExtractor | None = None,
    ) -> None:
        self.session = session
        self.speech_service = speech_service or build_speech_service()
        self.extractor = extractor or ClinicalTextExtractor()
        self.encounters = EncounterRepository(session)
        self.observations = ObservationRepository(session)
        self.transcriptions = SpeechTranscriptionRepository(session)

    def ingest(
        self,
        *,
        encounter_id: str,
        content: bytes,
        content_type: str,
        filename: str,
        actor: str = "kiosk-user",
    ) -> SpeechTranscription:
        encounter = self.encounters.get(encounter_id)
        if encounter is None:
            raise EntityNotFoundError("encounter", encounter_id)
        normalized_type = content_type.split(";", 1)[0].strip().casefold()
        validate_audio_signature(content, normalized_type)
        clean_name = safe_filename(filename)
        result = self.speech_service.transcribe(
            content, filename=clean_name, content_type=normalized_type
        )
        extracted = self.extractor.extract(result.transcript)
        existing = self.observations.list_symptoms(encounter_id)
        conflicts = self._conflicts(extracted, existing)
        row = self.transcriptions.add(
            SpeechTranscription(
                encounter_id=encounter_id,
                original_filename=filename[:255],
                safe_filename=clean_name,
                content_type=normalized_type,
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
                source=ObservationSource.SPEECH,
                processing_status="COMPLETED",
                transcript=result.transcript,
                provider=result.provider,
                model=result.model,
                language=result.language,
                confidence_metadata=result.confidence_metadata,
                extracted_symptoms=[item.as_dict() for item in extracted],
                conflicts=conflicts,
                symptom_ids=[],
                transcription_latency_ms=result.latency_ms,
            )
        )
        symptom_ids: list[str] = []
        for item in extracted:
            symptom = self.observations.add_symptom(
                Symptom(
                    encounter_id=encounter_id,
                    name=item.name,
                    present=item.present,
                    source=ObservationSource.SPEECH,
                )
            )
            symptom_ids.append(symptom.id)
        row.symptom_ids = symptom_ids
        record_audit_event(
            self.session,
            event_type="SPEECH_TRANSCRIPTION_PROCESSED",
            action="Transcribed clinician audio and extracted clinical text",
            actor=actor,
            patient_id=encounter.patient_id,
            encounter_id=encounter_id,
            metadata={
                "transcription_id": row.id,
                "sha256": row.sha256,
                "provider": row.provider,
                "model": row.model,
                "extracted_symptom_count": len(extracted),
                "conflict_count": len(conflicts),
            },
        )
        self.session.commit()
        self.session.refresh(row)
        return row

    def get(self, transcription_id: str) -> SpeechTranscription:
        row = self.transcriptions.get(transcription_id)
        if row is None:
            raise EntityNotFoundError("speech transcription", transcription_id)
        return row

    def list(self, encounter_id: str) -> list[SpeechTranscription]:
        if self.encounters.get(encounter_id) is None:
            raise EntityNotFoundError("encounter", encounter_id)
        return self.transcriptions.list_for_encounter(encounter_id)

    @staticmethod
    def _conflicts(extracted: list[Any], existing: list[Symptom]) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        by_name: dict[str, list[Symptom]] = {}
        for symptom in existing:
            by_name.setdefault(normalized_symptom_name(symptom.name), []).append(symptom)
        for item in extracted:
            for symptom in by_name.get(normalized_symptom_name(item.name), []):
                if symptom.present == item.present:
                    continue
                conflicts.append(
                    {
                        "field_type": "SYMPTOM",
                        "name": item.name,
                        "existing_observation_id": symptom.id,
                        "existing_source": symptom.source.value,
                        "existing_present": symptom.present,
                        "speech_present": item.present,
                        "resolution": "PRESERVED_BOTH_REVIEW_REQUIRED",
                    }
                )
        return conflicts

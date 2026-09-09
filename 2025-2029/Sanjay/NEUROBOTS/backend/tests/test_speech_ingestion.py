from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.routes.speech import get_speech_service
from app.core.enums import ObservationSource
from app.core.exceptions import ClinicalApiError
from app.db.models import Symptom
from app.main import app
from app.multimodal.clinical_text import ClinicalTextExtractor
from app.multimodal.speech import (
    GeminiSpeechService,
    SpeechResult,
    SpeechService,
    provider_audio_filename,
)
from app.services.speech_ingestion import SpeechIngestionService
from tests.conftest import ApiClient


WAV_BYTES = b"RIFF\x10\x00\x00\x00WAVEfmt " + b"\x00" * 16


class FakeGeminiError(Exception):
    def __init__(self, status_code: int, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.response = SimpleNamespace(headers=headers or {}, status_code=status_code)


class ScriptedSpeechService(SpeechService):
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript

    def transcribe(
        self, content: bytes, *, filename: str, content_type: str
    ) -> SpeechResult:
        assert content.startswith(b"RIFF")
        return SpeechResult(
            transcript=self.transcript,
            provider="scripted-test-stt",
            model="scripted-whisper",
            language="en",
            confidence_metadata={"available": True, "value": 0.93},
            latency_ms=12.5,
        )


def test_clinical_text_extractor_preserves_negation() -> None:
    findings = ClinicalTextExtractor().extract(
        "Patient reports chest pressure and nausea. Denies vomiting and has no shortness of breath."
    )
    indexed = {item.name: item for item in findings}

    assert indexed["chest pain"].present is True
    assert indexed["nausea"].present is True
    assert indexed["vomiting"].present is False
    assert indexed["shortness of breath"].present is False
    assert indexed["shortness of breath"].negation == "no"


def test_provider_audio_filename_matches_content_type() -> None:
    assert provider_audio_filename("browser-recording.webm", "audio/mp4") == "browser-recording.m4a"
    assert provider_audio_filename("voice.m4a", "audio/mp4") == "voice.m4a"
    assert provider_audio_filename("voice-note", "audio/mpeg") == "voice-note.mp3"


def test_speech_provider_reports_exhausted_rate_limit() -> None:
    exception = FakeGeminiError(429, headers={"retry-after": "3"})

    def generate_content(**_kwargs):
        raise exception

    client = SimpleNamespace(
        files=SimpleNamespace(
            upload=lambda **_kwargs: SimpleNamespace(name="uploaded-audio"),
            delete=lambda **_kwargs: None,
        ),
        models=SimpleNamespace(generate_content=generate_content),
    )
    service = GeminiSpeechService(api_key="test-only-key", client=client)

    with pytest.raises(ClinicalApiError) as caught:
        service.transcribe(WAV_BYTES, filename="voice.wav", content_type="audio/wav")

    assert caught.value.code == "SPEECH_PROVIDER_RATE_LIMITED"
    assert caught.value.status_code == 429
    assert "Retry after 3 seconds" in caught.value.detail


def test_speech_ingestion_preserves_manual_conflict_and_provenance(
    db_session, patient_payload
) -> None:
    from app.schemas.clinical import EncounterCreate, PatientCreate
    from app.services.encounters import EncounterService
    from app.services.patients import PatientService

    patient = PatientService(db_session).create(PatientCreate(**patient_payload))
    encounter = EncounterService(db_session).create(
        patient.id,
        EncounterCreate(encounter_type="emergency", chief_complaint="Chest pain"),
    )
    manual = Symptom(
        encounter_id=encounter.id,
        name="shortness of breath",
        present=True,
        source=ObservationSource.MANUAL,
    )
    db_session.add(manual)
    db_session.commit()

    transcription = SpeechIngestionService(
        db_session,
        speech_service=ScriptedSpeechService(
            "The patient has no shortness of breath but reports nausea."
        ),
    ).ingest(
        encounter_id=encounter.id,
        content=WAV_BYTES,
        content_type="audio/wav",
        filename="../../intake voice.wav",
    )

    symptoms = SpeechIngestionService(db_session).observations.list_symptoms(encounter.id)
    assert transcription.safe_filename == "intake_voice.wav"
    assert transcription.source == ObservationSource.SPEECH
    assert transcription.model == "scripted-whisper"
    assert len(transcription.symptom_ids) == 2
    assert [item.source for item in symptoms] == [ObservationSource.MANUAL, ObservationSource.SPEECH, ObservationSource.SPEECH]
    assert transcription.conflicts == [
        {
            "field_type": "SYMPTOM",
            "name": "shortness of breath",
            "existing_observation_id": manual.id,
            "existing_source": "MANUAL",
            "existing_present": True,
            "speech_present": False,
            "resolution": "PRESERVED_BOTH_REVIEW_REQUIRED",
        }
    ]


def test_speech_api_and_workflow_use_real_persisted_transcript(
    client: ApiClient, encounter: dict
) -> None:
    async def scripted_service() -> SpeechService:
        return ScriptedSpeechService(
            "Patient reports chest pressure and sweating, with no shortness of breath."
        )

    app.dependency_overrides[get_speech_service] = scripted_service
    try:
        manual = client.post(
            f"/api/encounters/{encounter['id']}/symptoms",
            json={"name": "shortness of breath", "present": True, "source": "MANUAL"},
        )
        assert manual.status_code == 201
        response = client.post(
            f"/api/encounters/{encounter['id']}/speech",
            content=WAV_BYTES,
            headers={"Content-Type": "audio/wav", "X-Filename": "voice note.wav"},
        )
        assert response.status_code == 201
        result = response.json()
        assert result["provider"] == "scripted-test-stt"
        assert result["source"] == "SPEECH"
        assert {item["name"] for item in result["extracted_symptoms"]} == {
            "chest pain",
            "sweating",
            "shortness of breath",
        }
        assert next(
            item for item in result["extracted_symptoms"] if item["name"] == "shortness of breath"
        )["present"] is False
        assert result["conflicts"][0]["resolution"] == "PRESERVED_BOTH_REVIEW_REQUIRED"

        listed = client.get(f"/api/encounters/{encounter['id']}/speech")
        fetched = client.get(f"/api/speech/{result['id']}")
        assert [item["id"] for item in listed.json()] == [result["id"]]
        assert fetched.json()["transcript"] == result["transcript"]

        workflow = client.post(f"/api/encounters/{encounter['id']}/workflow").json()
        assert workflow["transcript"] == result["transcript"]
        assert workflow["speech_results"][0]["transcription_id"] == result["id"]
        assert workflow["capability_status"]["speech_transcription"]["status"] == "AVAILABLE"
        current_dyspnea = next(
            item
            for item in workflow["fused_context"]["symptoms"]
            if item["name"] == "shortness of breath"
        )
        assert current_dyspnea["id"] == manual.json()["id"]
        assert workflow["fused_context"]["multimodal_conflicts"]
    finally:
        app.dependency_overrides.pop(get_speech_service, None)


def test_speech_api_reports_missing_provider_without_affecting_other_apis(
    client: ApiClient, encounter: dict
) -> None:
    response = client.post(
        f"/api/encounters/{encounter['id']}/speech",
        content=WAV_BYTES,
        headers={"Content-Type": "audio/wav", "X-Filename": "voice.wav"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SPEECH_PROVIDER_UNAVAILABLE"
    assert client.get(f"/api/encounters/{encounter['id']}").status_code == 200

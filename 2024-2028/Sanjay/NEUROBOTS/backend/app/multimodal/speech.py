from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import perf_counter
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import ClinicalApiError
from app.llm.gemini_provider import _error_status_code, _retry_after_seconds


@dataclass(frozen=True, slots=True)
class SpeechResult:
    transcript: str
    provider: str
    model: str
    language: str
    confidence_metadata: dict[str, Any]
    latency_ms: float


class SpeechService(ABC):
    @abstractmethod
    def transcribe(
        self, content: bytes, *, filename: str, content_type: str
    ) -> SpeechResult:
        """Transcribe audio only; diagnosis and clinical extraction are separate."""


class GeminiSpeechService(SpeechService):
    provider_name = "gemini"
    supported_content_types = {
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/mp4",
        "audio/x-m4a",
        "audio/ogg",
        "audio/webm",
        "audio/flac",
    }

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-3.6-flash",
        timeout_seconds: float = 45.0,
        max_retries: int = 2,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip() or "gemini-3.6-flash"
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._client = client

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def client(self) -> Any:
        if not self.available:
            raise ClinicalApiError(
                "SPEECH_PROVIDER_UNAVAILABLE",
                "Speech transcription is unavailable because GEMINI_API_KEY is not configured",
                503,
            )
        if self._client is None:
            try:
                from google import genai
            except ModuleNotFoundError as exception:
                raise ClinicalApiError(
                    "SPEECH_PROVIDER_UNAVAILABLE",
                    "Speech transcription is unavailable because google-genai is not installed",
                    503,
                ) from exception
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def transcribe(
        self, content: bytes, *, filename: str, content_type: str
    ) -> SpeechResult:
        validate_audio_signature(content, content_type)
        if not self.available:
            _ = self.client
        timer = perf_counter()
        uploaded_file = None
        temp_path: str | None = None
        try:
            suffix = Path(provider_audio_filename(filename, content_type)).suffix or ".bin"
            with NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                handle.write(content)
                temp_path = handle.name
            uploaded_file = self.client.files.upload(file=temp_path)
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    "Generate a verbatim English transcript of the speech. Return only the transcript text.",
                    uploaded_file,
                ],
                config={"http_options": {"timeout": self.timeout_seconds}},
            )
        except Exception as exception:
            status_code = _error_status_code(exception)
            if "timeout" in type(exception).__name__.casefold():
                raise ClinicalApiError(
                    "SPEECH_PROVIDER_TIMEOUT", "Speech transcription timed out", 504
                ) from exception
            if status_code == 429:
                retry_after = _retry_after_seconds(exception)
                suffix = f" Retry after {retry_after} seconds." if retry_after else ""
                raise ClinicalApiError(
                    "SPEECH_PROVIDER_RATE_LIMITED",
                    f"Speech transcription rate limit reached.{suffix}",
                    429,
                ) from exception
            if status_code in {400, 415, 422}:
                raise ClinicalApiError(
                    "SPEECH_AUDIO_REJECTED",
                    (
                        "The speech provider could not decode this audio. Try a valid WAV, MP3, "
                        "M4A, OGG, WebM, or FLAC recording."
                    ),
                    422,
                ) from exception
            if status_code in {500, 502, 503, 504} or "connection" in type(exception).__name__.casefold():
                raise ClinicalApiError(
                    "SPEECH_PROVIDER_FAILURE",
                    "Could not connect to the speech transcription provider",
                    503,
                ) from exception
            if isinstance(exception, ClinicalApiError):
                raise
            raise ClinicalApiError(
                "SPEECH_PROVIDER_FAILURE",
                f"Speech transcription failed ({type(exception).__name__})",
                503,
            ) from exception
        finally:
            if uploaded_file is not None and hasattr(self.client, "files"):
                try:
                    self.client.files.delete(name=uploaded_file.name)
                except Exception:
                    pass
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass
        transcript = str(getattr(response, "text", "")).strip()
        if not transcript:
            raise ClinicalApiError(
                "SPEECH_EMPTY_TRANSCRIPT", "Speech provider returned no transcript", 422
            )
        return SpeechResult(
            transcript=transcript,
            provider=self.provider_name,
            model=self.model,
            language="en",
            confidence_metadata={
                "available": False,
                "reason": "Provider response does not expose calibrated confidence",
            },
            latency_ms=round((perf_counter() - timer) * 1000, 3),
        )


def build_speech_service() -> SpeechService:
    settings = get_settings()
    return GeminiSpeechService(
        api_key=settings.gemini_api_key.get_secret_value(),
        model=settings.gemini_speech_model,
        timeout_seconds=settings.speech_timeout_seconds,
        max_retries=settings.gemini_max_retries,
    )


async def get_speech_service() -> SpeechService:
    return build_speech_service()


def validate_audio_signature(content: bytes, content_type: str) -> None:
    normalized = content_type.split(";", 1)[0].strip().casefold()
    if normalized not in GeminiSpeechService.supported_content_types:
        raise ClinicalApiError(
            "UNSUPPORTED_AUDIO_TYPE",
            "Supported audio types are WAV, MP3, MP4/M4A, OGG, WebM, and FLAC",
            415,
        )
    checks = {
        "audio/wav": lambda data: data.startswith(b"RIFF") and data[8:12] == b"WAVE",
        "audio/x-wav": lambda data: data.startswith(b"RIFF") and data[8:12] == b"WAVE",
        "audio/mpeg": _is_mp3,
        "audio/mp3": _is_mp3,
        "audio/mp4": lambda data: data[4:8] == b"ftyp",
        "audio/x-m4a": lambda data: data[4:8] == b"ftyp",
        "audio/ogg": lambda data: data.startswith(b"OggS"),
        "audio/webm": lambda data: data.startswith(b"\x1aE\xdf\xa3"),
        "audio/flac": lambda data: data.startswith(b"fLaC"),
    }
    if not content or not checks[normalized](content[:16]):
        raise ClinicalApiError(
            "AUDIO_SIGNATURE_MISMATCH",
            "The upload content does not match its declared audio type",
            415,
        )


def provider_audio_filename(filename: str, content_type: str) -> str:
    """Give the provider an extension consistent with the validated media type."""
    normalized = content_type.split(";", 1)[0].strip().casefold()
    allowed_extensions = {
        "audio/wav": {".wav"},
        "audio/x-wav": {".wav"},
        "audio/mpeg": {".mp3", ".mpeg", ".mpga"},
        "audio/mp3": {".mp3"},
        "audio/mp4": {".m4a", ".mp4"},
        "audio/x-m4a": {".m4a", ".mp4"},
        "audio/ogg": {".ogg"},
        "audio/webm": {".webm"},
        "audio/flac": {".flac"},
    }
    fallback_extensions = {
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/mp4": ".m4a",
        "audio/x-m4a": ".m4a",
        "audio/ogg": ".ogg",
        "audio/webm": ".webm",
        "audio/flac": ".flac",
    }
    path = Path(filename)
    if path.suffix.casefold() in allowed_extensions.get(normalized, set()):
        return filename
    stem = path.stem or "clinical-audio"
    return f"{stem}{fallback_extensions.get(normalized, '.audio')}"


def _is_mp3(data: bytes) -> bool:
    return data.startswith(b"ID3") or (
        len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0
    )

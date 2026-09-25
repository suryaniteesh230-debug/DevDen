from __future__ import annotations

import csv
import io
import re
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Callable, Sequence

from app.core.config import get_settings
from app.core.exceptions import ClinicalApiError


@dataclass(frozen=True, slots=True)
class OCRResult:
    text: str
    confidence: float | None
    engine: str
    engine_version: str
    page_count: int


class OCRService(ABC):
    @abstractmethod
    def extract(self, content: bytes, content_type: str) -> OCRResult:
        """Extract printed text without interpreting it clinically."""


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


class TesseractOCRService(OCRService):
    """Local Tesseract adapter independent of HTTP, persistence, and LangGraph."""

    supported_content_types = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/tiff": ".tiff",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }

    def __init__(
        self,
        *,
        tesseract_command: str | None = None,
        pdftoppm_command: str | None = None,
        timeout_seconds: float | None = None,
        max_pdf_pages: int | None = None,
        runner: RunCommand = subprocess.run,
    ) -> None:
        settings = get_settings()
        self.tesseract_command = tesseract_command or settings.tesseract_command
        self.pdftoppm_command = pdftoppm_command or settings.pdftoppm_command
        self.timeout_seconds = timeout_seconds or settings.ocr_timeout_seconds
        self.max_pdf_pages = max_pdf_pages or settings.ocr_max_pdf_pages
        self.runner = runner
        self._engine_version: str | None = None
        self._ocr_language: str | None = None

    def extract(self, content: bytes, content_type: str) -> OCRResult:
        normalized_type = content_type.split(";", 1)[0].strip().casefold()
        suffix = self.supported_content_types.get(normalized_type)
        if suffix is None:
            raise ClinicalApiError(
                "UNSUPPORTED_DOCUMENT_TYPE",
                "Supported document types are PNG, JPEG, TIFF, WebP, and PDF",
                415,
            )
        self._validate_signature(content, normalized_type)

        with tempfile.TemporaryDirectory(prefix="neurobots-ocr-") as temporary:
            root = Path(temporary)
            upload_path = root / f"upload{suffix}"
            upload_path.write_bytes(content)
            page_paths = (
                self._render_pdf(upload_path, root)
                if normalized_type == "application/pdf"
                else [upload_path]
            )
            page_results = [self._extract_page(path) for path in page_paths]

        texts = [text for text, _ in page_results if text]
        confidences = [value for _, values in page_results for value in values]
        return OCRResult(
            text="\n\n".join(texts).strip(),
            confidence=round(fmean(confidences) / 100.0, 4) if confidences else None,
            engine="tesseract",
            engine_version=f"{self._version()};lang={self._language()}",
            page_count=len(page_paths),
        )

    def _render_pdf(self, upload_path: Path, root: Path) -> list[Path]:
        prefix = root / "page"
        self._run(
            [
                self.pdftoppm_command,
                "-f",
                "1",
                "-l",
                str(self.max_pdf_pages),
                "-png",
                str(upload_path),
                str(prefix),
            ]
        )
        pages = sorted(root.glob("page-*.png"))
        if not pages:
            raise ClinicalApiError("OCR_FAILED", "The PDF contained no renderable pages", 422)
        return pages

    def _extract_page(self, path: Path) -> tuple[str, list[float]]:
        completed = self._run(
            [
                self.tesseract_command,
                str(path),
                "stdout",
                "-l",
                self._language(),
                "tsv",
            ]
        )
        reader = csv.DictReader(io.StringIO(completed.stdout), delimiter="\t")
        lines: dict[tuple[str, str, str, str], list[str]] = {}
        confidence_values: list[float] = []
        for row in reader:
            word = (row.get("text") or "").strip()
            if not word:
                continue
            key = tuple(row.get(name, "0") for name in ("block_num", "par_num", "line_num", "page_num"))
            lines.setdefault(key, []).append(word)
            try:
                confidence = float(row.get("conf", "-1"))
            except ValueError:
                continue
            if confidence >= 0:
                confidence_values.append(confidence)
        text = "\n".join(" ".join(words) for words in lines.values())
        return text, confidence_values

    def _version(self) -> str:
        if self._engine_version is None:
            output = self._run([self.tesseract_command, "--version"]).stdout.splitlines()
            first_line = output[0] if output else "tesseract unknown"
            match = re.search(r"tesseract\s+([^\s]+)", first_line, re.IGNORECASE)
            self._engine_version = match.group(1) if match else "unknown"
        return self._engine_version

    def _language(self) -> str:
        if self._ocr_language is None:
            lines = self._run([self.tesseract_command, "--list-langs"]).stdout.splitlines()
            installed = {line.strip() for line in lines[1:] if line.strip()}
            if "eng" in installed:
                self._ocr_language = "eng"
            elif "afr" in installed:
                self._ocr_language = "afr"
            else:
                raise ClinicalApiError(
                    "OCR_LANGUAGE_UNAVAILABLE",
                    "No supported Latin-script Tesseract language data is installed",
                    503,
                )
        return self._ocr_language

    def _run(self, arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            completed = self.runner(
                list(arguments),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except FileNotFoundError as exception:
            raise ClinicalApiError(
                "OCR_ENGINE_UNAVAILABLE", "The local OCR engine is not installed", 503
            ) from exception
        except subprocess.TimeoutExpired as exception:
            raise ClinicalApiError("OCR_TIMEOUT", "Local OCR processing timed out", 504) from exception
        if completed.returncode != 0:
            raise ClinicalApiError("OCR_FAILED", "The document could not be processed", 422)
        return completed

    @staticmethod
    def _validate_signature(content: bytes, content_type: str) -> None:
        signatures = {
            "image/png": lambda data: data.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/jpeg": lambda data: data.startswith(b"\xff\xd8\xff"),
            "image/tiff": lambda data: data.startswith((b"II*\x00", b"MM\x00*")),
            "image/webp": lambda data: data.startswith(b"RIFF") and data[8:12] == b"WEBP",
            "application/pdf": lambda data: data.startswith(b"%PDF-"),
        }
        if not content or not signatures[content_type](content[:16]):
            raise ClinicalApiError(
                "DOCUMENT_SIGNATURE_MISMATCH",
                "The upload content does not match its declared document type",
                415,
            )

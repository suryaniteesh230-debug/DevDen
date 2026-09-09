from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import UTC, datetime
from enum import StrEnum
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import Field, StringConstraints

from sahayi_api.procedures import (
    ExpectedSourceFormat,
    LoadedProcedure,
    SourceNormalizationVersion,
    SourceRecord,
    StrictModel,
)


USER_AGENT = "Sahayi-Procedure-Intelligence/1.0 (one-shot human-review prototype)"
MAX_REDIRECTS = 3
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class MonitorClassification(StrEnum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    UNREACHABLE = "unreachable"
    REDIRECT_BLOCKED = "redirect_blocked"
    CONTENT_TYPE_REJECTED = "content_type_rejected"
    OVERSIZED = "oversized"
    REVIEW_REQUIRED = "review_required"


class CandidateFingerprint(StrictModel):
    digest: Digest
    size: Annotated[int, Field(ge=0, le=5_000_000)]
    content_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    etag: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None
    last_modified: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None = None


class SourceReviewReport(StrictModel):
    service_id: str
    pack_version: str
    source_id: str
    url: str
    classification: MonitorClassification
    old_digest: Digest | None
    new_digest: Digest | None
    old_size: Annotated[int, Field(ge=0, le=5_000_000)] | None
    new_size: Annotated[int, Field(ge=0, le=5_000_000)] | None
    old_content_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None
    new_content_type: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)] | None
    etag: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None
    last_modified: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] | None
    normalization_version: SourceNormalizationVersion
    checked_at: datetime
    affected_references: Annotated[list[str], Field(max_length=60)]
    recommendation: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self.parts.append(data)


def normalize_html_text(value: bytes | str) -> str:
    text = value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value
    parser = _VisibleTextParser()
    parser.feed(text)
    parser.close()
    normalized = unicodedata.normalize("NFKC", " ".join(parser.parts))
    return re.sub(r"\s+", " ", normalized).strip()


def fingerprint_content(
    value: bytes,
    expected_format: ExpectedSourceFormat,
    normalization_version: SourceNormalizationVersion,
) -> tuple[str, int]:
    if expected_format is ExpectedSourceFormat.HTML:
        if normalization_version is not SourceNormalizationVersion.HTML_TEXT_V1:
            raise ValueError("Unsupported HTML normalization version")
        payload = normalize_html_text(value).encode("utf-8")
    else:
        if normalization_version is not SourceNormalizationVersion.PDF_BYTES_V1:
            raise ValueError("Unsupported PDF normalization version")
        payload = value
    return hashlib.sha256(payload).hexdigest(), len(payload)


def _safe_header(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > 200 or "\r" in cleaned or "\n" in cleaned:
        return None
    return cleaned


def _content_type(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def _accepted_content_type(expected: ExpectedSourceFormat, value: str) -> bool:
    if expected is ExpectedSourceFormat.PDF:
        return value == "application/pdf"
    return value in {"text/html", "application/xhtml+xml"}


def _affected_references(loaded: LoadedProcedure, source_id: str) -> list[str]:
    references: list[str] = []
    for key, source_ids in sorted(loaded.pack.provenance.items()):
        if source_id in source_ids:
            references.append(f"provenance:{key}")

    def walk(value: object, path: str) -> None:
        if len(references) >= 60:
            return
        if isinstance(value, dict):
            source_ids = value.get("source_ids")
            if isinstance(source_ids, list) and source_id in source_ids:
                references.append(path)
            for key, nested in value.items():
                if key not in {"sources", "localization", "provenance"}:
                    walk(nested, f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                walk(nested, f"{path}[{index}]")

    walk(loaded.pack.model_dump(mode="json"), "pack")
    return list(dict.fromkeys(references))[:60]


def _recommendation(classification: MonitorClassification) -> str:
    if classification is MonitorClassification.UNCHANGED:
        return "No source-content change was detected; retain the reviewed pack and record this check only after human review."
    if classification is MonitorClassification.CHANGED:
        return "Quarantine this candidate for human fact review. Do not replace facts, resolve conflicts, or activate a pack automatically."
    if classification is MonitorClassification.REVIEW_REQUIRED:
        return "A reviewed baseline is missing or incompatible. Establish it through an authorized human review before comparing changes."
    return "Retrieval did not produce an acceptable candidate. Keep the last reviewed pack active and investigate manually."


def _report(
    loaded: LoadedProcedure,
    source: SourceRecord,
    classification: MonitorClassification,
    candidate: CandidateFingerprint | None = None,
    *,
    checked_at: datetime | None = None,
) -> SourceReviewReport:
    policy = source.monitoring
    if policy is None:
        raise ValueError("Source monitoring is not configured")
    return SourceReviewReport(
        service_id=loaded.pack.service_id,
        pack_version=loaded.pack.pack_version,
        source_id=source.source_id,
        url=str(source.url),
        classification=classification,
        old_digest=policy.reviewed_fingerprint,
        new_digest=candidate.digest if candidate else None,
        old_size=policy.reviewed_size,
        new_size=candidate.size if candidate else None,
        old_content_type=policy.reviewed_content_type,
        new_content_type=candidate.content_type if candidate else None,
        etag=candidate.etag if candidate else None,
        last_modified=candidate.last_modified if candidate else None,
        normalization_version=policy.normalization_version,
        checked_at=checked_at or datetime.now(UTC),
        affected_references=_affected_references(loaded, source.source_id),
        recommendation=_recommendation(classification),
    )


def compare_candidate(
    loaded: LoadedProcedure,
    source: SourceRecord,
    candidate: CandidateFingerprint,
    *,
    checked_at: datetime | None = None,
) -> SourceReviewReport:
    policy = source.monitoring
    if policy is None or policy.reviewed_fingerprint is None:
        classification = MonitorClassification.REVIEW_REQUIRED
    elif candidate.digest == policy.reviewed_fingerprint:
        classification = MonitorClassification.UNCHANGED
    else:
        classification = MonitorClassification.CHANGED
    return _report(loaded, source, classification, candidate, checked_at=checked_at)


class SourceRetriever:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        self._attempted: set[tuple[str, str]] = set()

    def retrieve(self, loaded: LoadedProcedure, source: SourceRecord) -> SourceReviewReport:
        configured = next((item for item in loaded.pack.sources if item.source_id == source.source_id), None)
        if configured is None or str(configured.url) != str(source.url):
            raise ValueError("Source is not an exact allowlisted pack URL")
        attempt_key = (loaded.pack.service_id, source.source_id)
        if attempt_key in self._attempted:
            raise ValueError("A source may be retrieved at most once per invocation")
        self._attempted.add(attempt_key)
        policy = source.monitoring
        if policy is None:
            raise ValueError("Source monitoring is not configured")
        owns_client = self._client is None
        client = self._client or httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "text/html, application/xhtml+xml, application/pdf"},
            timeout=httpx.Timeout(8.0, connect=4.0),
            follow_redirects=False,
            transport=httpx.HTTPTransport(retries=0),
        )
        current_url = str(source.url)
        allowed_hosts = {source.url.host, *policy.allowed_redirect_hosts}
        checked_at = datetime.now(UTC)
        try:
            for redirect_count in range(MAX_REDIRECTS + 1):
                with client.stream(
                    "GET",
                    current_url,
                    headers={"User-Agent": USER_AGENT, "Accept": "text/html, application/xhtml+xml, application/pdf"},
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if location is None or redirect_count >= MAX_REDIRECTS:
                            return _report(loaded, source, MonitorClassification.REDIRECT_BLOCKED, checked_at=checked_at)
                        next_url = urljoin(current_url, location)
                        parsed = urlsplit(next_url)
                        if parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username or parsed.password:
                            return _report(loaded, source, MonitorClassification.REDIRECT_BLOCKED, checked_at=checked_at)
                        current_url = next_url
                        continue
                    if response.status_code >= 400:
                        return _report(loaded, source, MonitorClassification.UNREACHABLE, checked_at=checked_at)
                    media_type = _content_type(response.headers.get("content-type"))
                    if not _accepted_content_type(policy.expected_format, media_type):
                        return _report(loaded, source, MonitorClassification.CONTENT_TYPE_REJECTED, checked_at=checked_at)
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > policy.max_bytes:
                            return _report(loaded, source, MonitorClassification.OVERSIZED, checked_at=checked_at)
                        chunks.append(chunk)
                    digest, normalized_size = fingerprint_content(
                        b"".join(chunks), policy.expected_format, policy.normalization_version
                    )
                    candidate = CandidateFingerprint(
                        digest=digest,
                        size=normalized_size,
                        content_type=media_type,
                        etag=_safe_header(response.headers.get("etag")),
                        last_modified=_safe_header(response.headers.get("last-modified")),
                    )
                    return compare_candidate(loaded, source, candidate, checked_at=checked_at)
            return _report(loaded, source, MonitorClassification.REDIRECT_BLOCKED, checked_at=checked_at)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError):
            return _report(loaded, source, MonitorClassification.UNREACHABLE, checked_at=checked_at)
        finally:
            if owns_client:
                client.close()


def demo_fixture_path() -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "procedure_monitor_demo.json"


def load_demo_reports(registry: dict[str, LoadedProcedure], path: Path | None = None) -> list[SourceReviewReport]:
    payload = json.loads((path or demo_fixture_path()).read_text(encoding="utf-8"))
    loaded = registry[payload["service_id"]]
    source = next(item for item in loaded.pack.sources if item.source_id == payload["source_id"])
    reports: list[SourceReviewReport] = []
    for case in payload["cases"]:
        if case["classification"] == "unreachable":
            reports.append(_report(loaded, source, MonitorClassification.UNREACHABLE))
            continue
        candidate_bytes = case["candidate_html"].encode("utf-8")
        digest, size = fingerprint_content(candidate_bytes, ExpectedSourceFormat.HTML, SourceNormalizationVersion.HTML_TEXT_V1)
        candidate = CandidateFingerprint(digest=digest, size=size, content_type="text/html")
        policy = source.monitoring.model_copy(
            update={
                "reviewed_fingerprint": case["reviewed_fingerprint"],
                "reviewed_size": case["reviewed_size"],
                "reviewed_at": datetime.fromisoformat(case["reviewed_at"]),
                "reviewed_content_type": "text/html",
            }
        )
        demo_source = source.model_copy(update={"monitoring": policy})
        reports.append(compare_candidate(loaded, demo_source, candidate))
    return reports


def report_exit_code(reports: list[SourceReviewReport]) -> int:
    return 0 if reports and all(report.classification is MonitorClassification.UNCHANGED for report in reports) else 2


def report_json(reports: list[SourceReviewReport]) -> str:
    return json.dumps([report.model_dump(mode="json") for report in reports], ensure_ascii=False, indent=2) + "\n"


def report_text(reports: list[SourceReviewReport]) -> str:
    lines = ["Sahayi one-shot Procedure Intelligence review report"]
    for report in reports:
        lines.extend(
            [
                f"- {report.service_id} pack {report.pack_version} / {report.source_id}: {report.classification.value}",
                f"  URL: {report.url}",
                f"  Old digest: {report.old_digest or 'not reviewed'}",
                f"  New digest: {report.new_digest or 'unavailable'}",
                f"  Affected references: {', '.join(report.affected_references) or 'none'}",
                f"  Recommendation: {report.recommendation}",
            ]
        )
    return "\n".join(lines) + "\n"

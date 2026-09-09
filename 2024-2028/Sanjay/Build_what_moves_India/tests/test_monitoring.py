from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from sahayi_api.monitoring import (
    CandidateFingerprint,
    MonitorClassification,
    SourceRetriever,
    USER_AGENT,
    compare_candidate,
    fingerprint_content,
    load_demo_reports,
    normalize_html_text,
)
from sahayi_api.procedure_tool import monitor_sources
from sahayi_api.procedures import (
    ExpectedSourceFormat,
    SourceNormalizationVersion,
    default_pack_root,
    load_procedure_registry,
)


REGISTRY = load_procedure_registry(default_pack_root())
LOADED = REGISTRY["uidai-aadhaar-address-update"]
SOURCE = LOADED.pack.sources[0]


def _baseline_source(body: bytes = b"<p>Verified demo wording</p>"):
    digest, size = fingerprint_content(body, ExpectedSourceFormat.HTML, SourceNormalizationVersion.HTML_TEXT_V1)
    policy = SOURCE.monitoring.model_copy(
        update={"reviewed_fingerprint": digest, "reviewed_size": size, "reviewed_at": datetime(2026, 8, 28, tzinfo=UTC), "reviewed_content_type": "text/html"}
    )
    return SOURCE.model_copy(update={"monitoring": policy})


def _retrieve(handler, source=None):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        return SourceRetriever(client).retrieve(LOADED, source or SOURCE)
    finally:
        client.close()


def test_html_normalization_and_fingerprint_are_deterministic() -> None:
    first = b"<html><style>x</style><body>A&nbsp; fee <!-- ignored -->\n <b>statement</b><script>bad()</script></body></html>"
    second = "<p>A fee statement</p>"
    assert normalize_html_text(first) == "A fee statement"
    assert normalize_html_text(second) == "A fee statement"
    assert fingerprint_content(first, ExpectedSourceFormat.HTML, SourceNormalizationVersion.HTML_TEXT_V1) == fingerprint_content(
        second.encode(), ExpectedSourceFormat.HTML, SourceNormalizationVersion.HTML_TEXT_V1
    )


def test_compare_classifies_unchanged_changed_and_review_required_without_pack_mutation() -> None:
    original = LOADED.pack.model_dump_json()
    reviewed = _baseline_source()
    old_digest = reviewed.monitoring.reviewed_fingerprint
    unchanged = compare_candidate(
        LOADED,
        reviewed,
        CandidateFingerprint(digest=old_digest, size=22, content_type="text/html"),
    )
    changed = compare_candidate(
        LOADED,
        reviewed,
        CandidateFingerprint(digest="a" * 64, size=24, content_type="text/html"),
    )
    missing = compare_candidate(
        LOADED,
        SOURCE,
        CandidateFingerprint(digest="b" * 64, size=24, content_type="text/html"),
    )
    assert unchanged.classification == "unchanged"
    assert changed.classification == "changed"
    assert "Quarantine" in changed.recommendation
    assert changed.affected_references
    assert missing.classification == "review_required"
    assert LOADED.pack.model_dump_json() == original


def test_retrieval_uses_exact_allowlist_safe_headers_one_attempt_and_no_credentials() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, headers={"content-type": "text/html", "etag": "demo-etag"}, content=b"<p>Candidate</p>")

    retriever = SourceRetriever(httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        report = retriever.retrieve(LOADED, SOURCE)
        with pytest.raises(ValueError, match="at most once"):
            retriever.retrieve(LOADED, SOURCE)
    finally:
        retriever._client.close()
    assert report.classification == "review_required"
    assert len(requests) == 1
    assert requests[0].headers["user-agent"] == USER_AGENT
    assert "authorization" not in requests[0].headers
    assert "cookie" not in requests[0].headers

    altered = SOURCE.model_copy(update={"url": "https://example.gov.invalid/source"})
    with pytest.raises(ValueError, match="exact allowlisted"):
        SourceRetriever(httpx.Client(transport=httpx.MockTransport(handler))).retrieve(LOADED, altered)


def test_redirect_downgrade_and_unapproved_host_are_blocked_without_following() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(302, headers={"location": "http://attacker.invalid/next"})

    report = _retrieve(handler)
    assert report.classification == "redirect_blocked"
    assert calls == 1


@pytest.mark.parametrize(
    ("handler", "classification"),
    [
        (lambda request: httpx.Response(200, headers={"content-type": "application/json"}, content=b"{}"), "content_type_rejected"),
        (lambda request: httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 1_000_001), "oversized"),
        (lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("timeout", request=request)), "unreachable"),
    ],
)
def test_wrong_content_type_oversized_and_timeout_fail_closed(handler, classification: str) -> None:
    assert _retrieve(handler).classification == classification


def test_offline_demo_is_default_changed_is_quarantined_and_live_requires_acknowledgement(capsys) -> None:
    reports = load_demo_reports(REGISTRY)
    assert [report.classification for report in reports] == [
        MonitorClassification.UNCHANGED,
        MonitorClassification.CHANGED,
        MonitorClassification.UNREACHABLE,
    ]
    assert monitor_sources(
        pack_root=default_pack_root(),
        live=False,
        acknowledged=False,
        source_ids=[],
        fixture=None,
        json_output=True,
        output=None,
    ) == 2
    assert '"classification": "changed"' in capsys.readouterr().out
    assert monitor_sources(
        pack_root=default_pack_root(),
        live=True,
        acknowledged=False,
        source_ids=[],
        fixture=None,
        json_output=False,
        output=None,
    ) == 2
    assert "requires --acknowledge" in capsys.readouterr().out


def test_report_json_contains_metadata_not_candidate_content() -> None:
    serialized = json.dumps([report.model_dump(mode="json") for report in load_demo_reports(REGISTRY)])
    assert "Demo form wording version two" not in serialized
    assert "old_digest" in serialized
    assert '"service_id": "uidai-aadhaar-address-update"' in serialized
    assert "new_digest" in serialized

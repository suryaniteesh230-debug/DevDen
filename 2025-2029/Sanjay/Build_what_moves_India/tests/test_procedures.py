from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

import sahayi_api.main as main_module
from sahayi_api.main import app
from sahayi_api.procedure_tool import schema_text
from sahayi_api.procedures import (
    LifecycleStatus,
    PackLoadError,
    ProcedurePack,
    TrustState,
    default_pack_root,
    load_procedure_registry,
    pack_digest,
    required_translation_keys,
    summarize_procedure,
)

PACK_PATH = default_pack_root() / "uidai-aadhaar-address-update" / "1.5.0" / "pack.json"
KERALA_PACK_PATH = default_pack_root() / "kerala-ign-oap" / "1.3.0" / "pack.json"
SCHEMA_PATH = PACK_PATH.parents[3] / "schemas" / "procedure-pack-v1.schema.json"


def pack_data() -> dict[str, object]:
    return json.loads(PACK_PATH.read_text(encoding="utf-8"))


def write_pack(root: Path, name: str, data: dict[str, object]) -> None:
    target = root / name / "pack.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(data), encoding="utf-8")


def confirmed_fee() -> dict[str, object]:
    return {
        "verification_status": "confirmed",
        "amount": "50.00",
        "currency": "INR",
        "display_message": "Official sources agree on the fee.",
        "claims": [
            {
                "amount": "50.00",
                "currency": "INR",
                "qualifier": "Online address update, including GST.",
                "source_ids": ["uidai-enrolment-update-faq"],
            }
        ],
        "resolution_guidance": None,
        "source_ids": ["uidai-enrolment-update-faq"],
    }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as api_client:
        yield api_client


def test_valid_pack_loads() -> None:
    registry = load_procedure_registry(default_pack_root())
    loaded = registry["uidai-aadhaar-address-update"]
    assert loaded.pack.status is LifecycleStatus.ACTIVE
    assert loaded.pack.title["en"] == "Update your Aadhaar address online"


def test_two_active_packs_are_independently_versioned_and_verified() -> None:
    registry = load_procedure_registry(default_pack_root())
    kerala = registry["kerala-ign-oap"]
    aadhaar = registry["uidai-aadhaar-address-update"]
    assert kerala.pack.pack_version == "1.3.0"
    assert kerala.digest != aadhaar.digest
    assert kerala.pack.jurisdiction.name == "Kerala"
    assert {source.source_id for source in kerala.pack.sources} == {
        "kerala-sevana-criteria", "kerala-sevana-application-forms", "kerala-ign-oap-application-form"
    }
    assert kerala.pack.fee.verification_status.value == "not_stated"
    assert kerala.pack.fee.amount is None
    assert "pension amount" not in " ".join(item.text.lower() for item in kerala.pack.requirements)
    assert all(question.sensitivity.value == "sensitive" for question in kerala.pack.readiness.questions[2:])
    assert len(kerala.pack.readiness.additional_review_items) == 3


@pytest.mark.parametrize(
    ("previous", "current"),
    [
        (default_pack_root() / "uidai-aadhaar-address-update" / "1.4.0" / "pack.json", PACK_PATH),
        (default_pack_root() / "kerala-ign-oap" / "1.2.0" / "pack.json", KERALA_PACK_PATH),
    ],
)
def test_monitoring_version_bumps_preserve_all_canonical_facts(previous: Path, current: Path) -> None:
    def canonical(path: Path) -> dict[str, object]:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("pack_version")
        data.pop("status")
        for source in data["sources"]:
            source.pop("monitoring", None)
        for field in data["assistance"]["preparation_fields"]:
            for key in (
                "question_id", "question", "why_needed", "input_type", "required", "validation",
                "supported_value_sources", "may_appear_on_sheet", "confirmation_required", "editable",
                "choices", "readiness_question_id", "document_ids",
            ):
                field.pop(key, None)
        return data

    assert canonical(previous) == canonical(current)


def test_checked_in_json_schema_matches_model() -> None:
    assert SCHEMA_PATH.read_text(encoding="utf-8") == schema_text()


def test_unknown_fields_and_html_are_rejected() -> None:
    unknown = pack_data()
    unknown["unexpected"] = True
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ProcedurePack.model_validate(unknown)

    html = pack_data()
    html["title"] = {"en": "<strong>Unsafe</strong>"}
    with pytest.raises(ValidationError, match="HTML content is not permitted"):
        ProcedurePack.model_validate(html)


def test_identifier_shaped_synthetic_demo_values_are_rejected() -> None:
    data = pack_data()
    data["assistance"]["preparation_fields"][0]["demo_value"] = {
        "en": "1234 5678 9012",
        "hi": "१२३४ ५६७८ ९०१२",
        "ml": "൧൨൩൪ ൫൬൭൮ ൯൦൧൨",
    }
    with pytest.raises(ValidationError, match="identifier-shaped"):
        ProcedurePack.model_validate(data)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.update(review_due_at="2026-01-01T00:00:00Z"), "review_due_at must be after"),
        (lambda data: data["sources"][0].update(url="http://uidai.gov.in/example"), "must use HTTPS"),
        (lambda data: data.update(official_handoff_url="http://myaadhaar.uidai.gov.in"), "must use HTTPS"),
    ],
)
def test_invalid_dates_and_non_https_urls_are_rejected(mutation, message: str) -> None:
    data = pack_data()
    mutation(data)
    with pytest.raises(ValidationError, match=message):
        ProcedurePack.model_validate(data)


def test_monitoring_metadata_is_strict_complete_and_only_for_referenced_sources() -> None:
    incomplete = pack_data()
    incomplete["sources"][0]["monitoring"]["reviewed_fingerprint"] = "a" * 64
    with pytest.raises(ValidationError, match="fingerprint, timestamp, size, and content type"):
        ProcedurePack.model_validate(incomplete)

    wrong_normalization = pack_data()
    wrong_normalization["sources"][0]["monitoring"]["normalization_version"] = "pdf-bytes-v1"
    with pytest.raises(ValidationError, match="HTML sources require html-text-v1"):
        ProcedurePack.model_validate(wrong_normalization)

    credentials = pack_data()
    credentials["sources"][0]["url"] = "https://user:password@uidai.gov.in/example"
    with pytest.raises(ValidationError, match="must not include credentials"):
        ProcedurePack.model_validate(credentials)

    ip_host = pack_data()
    ip_host["sources"][0]["url"] = "https://127.0.0.1/example"
    with pytest.raises(ValidationError, match="public DNS names"):
        ProcedurePack.model_validate(ip_host)

    unreferenced = pack_data()
    extra = copy.deepcopy(unreferenced["sources"][0])
    extra.update(source_id="unreferenced-monitor-source", url="https://uidai.gov.in/unreferenced-monitor-source")
    unreferenced["sources"].append(extra)
    with pytest.raises(ValidationError, match="monitoring configured for unreferenced sources"):
        ProcedurePack.model_validate(unreferenced)


def test_missing_and_nonexistent_source_references_are_rejected() -> None:
    missing = pack_data()
    del missing["fee"]["source_ids"]
    with pytest.raises(ValidationError, match="Field required"):
        ProcedurePack.model_validate(missing)

    nonexistent = pack_data()
    nonexistent["provenance"]["fee"] = ["not-a-source"]
    with pytest.raises(ValidationError, match="unknown source references"):
        ProcedurePack.model_validate(nonexistent)

    unmapped = pack_data()
    del unmapped["provenance"]["fee"]
    with pytest.raises(ValidationError, match="missing provenance mappings: fee"):
        ProcedurePack.model_validate(unmapped)


def test_confirmed_fee_validation() -> None:
    data = pack_data()
    data["status"] = "superseded"
    data["fee"] = confirmed_fee()
    validated = ProcedurePack.model_validate(data)
    assert validated.fee.verification_status == "confirmed"
    assert str(validated.fee.amount) == "50.00"


def test_conflicting_fee_validation_and_distinct_claims() -> None:
    validated = ProcedurePack.model_validate(pack_data())
    assert validated.fee.verification_status == "conflicting"
    assert validated.fee.amount is None

    duplicate = pack_data()
    duplicate["fee"]["claims"][1]["amount"] = "50.00"
    with pytest.raises(ValidationError, match="at least two distinct claims with different values"):
        ProcedurePack.model_validate(duplicate)


def test_conflicting_fee_rejects_a_canonical_amount() -> None:
    data = pack_data()
    data["fee"]["amount"] = "50.00"
    data["fee"]["currency"] = "INR"
    with pytest.raises(ValidationError, match="must not expose a canonical amount"):
        ProcedurePack.model_validate(data)


def test_fee_claim_provenance_must_exist() -> None:
    data = pack_data()
    data["fee"]["claims"][0]["source_ids"] = ["not-a-source"]
    data["fee"]["source_ids"] = ["not-a-source", "uidai-my-aadhaar-services"]
    with pytest.raises(ValidationError, match="unknown source references: not-a-source"):
        ProcedurePack.model_validate(data)


def test_confirmed_fee_claims_cannot_disagree() -> None:
    data = pack_data()
    data["status"] = "superseded"
    fee = confirmed_fee()
    fee["claims"].append(
        {
            "amount": "75.00",
            "currency": "INR",
            "qualifier": "A second official statement.",
            "source_ids": ["uidai-my-aadhaar-services"],
        }
    )
    fee["source_ids"] = ["uidai-enrolment-update-faq", "uidai-my-aadhaar-services"]
    data["fee"] = fee
    with pytest.raises(ValidationError, match="confirmed fee claims must agree"):
        ProcedurePack.model_validate(data)


def test_free_and_not_stated_fee_validation() -> None:
    free = pack_data()
    free["status"] = "superseded"
    free["fee"] = {
        "verification_status": "free",
        "amount": "0.00",
        "currency": "INR",
        "display_message": "This service is free.",
        "claims": [{"amount": "0.00", "currency": "INR", "qualifier": "No fee is charged.", "source_ids": ["uidai-my-aadhaar-services"]}],
        "resolution_guidance": None,
        "source_ids": ["uidai-my-aadhaar-services"],
    }
    assert ProcedurePack.model_validate(free).fee.verification_status == "free"

    not_stated = pack_data()
    not_stated["status"] = "superseded"
    not_stated["fee"] = {
        "verification_status": "not_stated",
        "amount": None,
        "currency": None,
        "display_message": "The reviewed source does not state a fee.",
        "claims": [],
        "resolution_guidance": None,
        "source_ids": ["uidai-update-overview"],
    }
    assert ProcedurePack.model_validate(not_stated).fee.verification_status == "not_stated"
    not_stated["fee"]["amount"] = "1.00"
    with pytest.raises(ValidationError, match="not_stated fee must not include an amount"):
        ProcedurePack.model_validate(not_stated)


def test_duplicate_service_version_is_rejected(tmp_path: Path) -> None:
    data = pack_data()
    write_pack(tmp_path, "one", data)
    write_pack(tmp_path, "two", data)
    with pytest.raises(PackLoadError, match="Duplicate procedure pack version"):
        load_procedure_registry(tmp_path)


def test_duplicate_active_versions_are_rejected(tmp_path: Path) -> None:
    first = pack_data()
    second = copy.deepcopy(first)
    second["pack_version"] = "1.6.0"
    write_pack(tmp_path, "one", first)
    write_pack(tmp_path, "two", second)
    with pytest.raises(PackLoadError, match="exactly one active"):
        load_procedure_registry(tmp_path)


def test_draft_pack_is_not_selected(tmp_path: Path) -> None:
    active = pack_data()
    draft = copy.deepcopy(active)
    draft["pack_version"] = "1.6.0"
    draft["status"] = "draft"
    write_pack(tmp_path, "active", active)
    write_pack(tmp_path, "draft", draft)
    registry = load_procedure_registry(tmp_path)
    assert registry[active["service_id"]].pack.pack_version == "1.5.0"


def test_no_active_pack_fails_closed(tmp_path: Path) -> None:
    draft = pack_data()
    draft["status"] = "draft"
    write_pack(tmp_path, "draft", draft)
    with pytest.raises(PackLoadError, match="No active"):
        load_procedure_registry(tmp_path)


def test_stale_trust_calculation() -> None:
    loaded = load_procedure_registry(default_pack_root())["uidai-aadhaar-address-update"]
    assert loaded.trust_state(datetime(2026, 9, 10, tzinfo=UTC)) is TrustState.CURRENT
    assert loaded.trust_state(datetime(2026, 9, 12, tzinfo=UTC)) is TrustState.STALE
    assert summarize_procedure(loaded, datetime(2026, 9, 10, tzinfo=UTC)).attention_required is True
    assert summarize_procedure(loaded, datetime(2026, 9, 12, tzinfo=UTC)).attention_required is True


def test_pack_digest_is_deterministic() -> None:
    original = ProcedurePack.model_validate(pack_data())
    reordered_json = json.dumps(pack_data(), sort_keys=True)
    reordered = ProcedurePack.model_validate_json(reordered_json)
    assert pack_digest(original) == pack_digest(reordered)
    assert pack_digest(original) == "c2ab0efb18104cff431ed717b4f3b5e89db0b8935369fddfbe2cdd8bc9ee7805"
    assert pack_digest(original) != "ddafaa94d2dd25ff39e1f4cd9e9153461f8627eae4ffd8b6a85ec979b20c4251"


def test_active_aadhaar_pack_never_presents_a_conflicting_amount_as_definitive() -> None:
    data = pack_data()
    assert data["fee"]["verification_status"] == "conflicting"
    assert data["fee"]["amount"] is None
    assert data["fee"]["currency"] is None
    citizen_guidance = " ".join(
        [data["fee"]["display_message"], data["fee"]["resolution_guidance"]]
        + [step["instruction"] for step in data["steps"]]
    )
    assert "fee is ₹50" not in citizen_guidance
    assert "fee is ₹75" not in citizen_guidance
    assert "official fee for an online address update is" not in citizen_guidance.lower()


@pytest.mark.anyio
async def test_list_endpoint_returns_safe_active_summaries(client: AsyncClient) -> None:
    response = await client.get("/api/v1/procedures")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["locale"] == "en"
    assert payload["translation"]["method"] == "canonical_source"
    assert len(payload["procedures"]) == 2
    summary = next(item for item in payload["procedures"] if item["service_id"] == "uidai-aadhaar-address-update")
    assert summary["service_id"] == "uidai-aadhaar-address-update"
    assert summary["intent_phrases"] == ["change Aadhaar address", "update address in Aadhaar", "moved to a new address"]
    assert summary["trust_state"] == "current"
    assert summary["attention_required"] is True
    assert "requirements" not in summary
    assert "official_handoff_url" not in summary
    assert "readiness" not in summary
    assert "sources" not in summary
    assert "provenance" not in summary


@pytest.mark.anyio
async def test_kerala_detail_exposes_sourced_form_and_respectful_review_items(client: AsyncClient) -> None:
    response = await client.get("/api/v1/procedures/kerala-ign-oap")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["fee"]["verification_status"] == "not_stated"
    assert payload["fee"]["amount"] is None
    assert payload["fee"]["claims"] == []
    assert payload["official_handoff_url"].endswith("ApplicationFormsEng.aspx")
    assert payload["submission_channels"][0]["name"] == "Local body of permanent residence"
    assert len(payload["additional_review_items"]) == 3
    assert "2000" not in json.dumps(payload)


@pytest.mark.anyio
async def test_detail_endpoint_returns_procedure_and_provenance(client: AsyncClient) -> None:
    response = await client.get("/api/v1/procedures/uidai-aadhaar-address-update")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["locale"] == "en"
    assert payload["fee"]["verification_status"] == "conflicting"
    assert payload["fee"]["amount"] is None
    assert payload["fee"]["currency"] is None
    assert [claim["amount"] for claim in payload["fee"]["claims"]] == ["50.00", "75.00"]
    assert payload["fee"]["resolution_guidance"].endswith("Confirm the fee on the official portal before payment.")
    assert payload["attention_required"] is True
    assert payload["official_handoff_url"] == "https://myaadhaar.uidai.gov.in/"
    assert payload["pack_digest"] == "c2ab0efb18104cff431ed717b4f3b5e89db0b8935369fddfbe2cdd8bc9ee7805"
    assert payload["provenance"]["fee"] == ["uidai-enrolment-update-faq", "uidai-my-aadhaar-services"]
    assert all(source["url"].startswith("https://") for source in payload["sources"])


@pytest.mark.anyio
async def test_unknown_service_is_safe_and_not_stored(client: AsyncClient) -> None:
    response = await client.get("/api/v1/procedures/not-supported")
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"error": "Procedure not found"}


def test_active_packs_have_exact_complete_translations() -> None:
    for loaded in load_procedure_registry(default_pack_root()).values():
        expected = required_translation_keys(loaded.pack)
        assert loaded.pack.localization is not None
        assert set(loaded.pack.localization.translations) == {"hi", "ml"}
        for locale in ("hi", "ml"):
            assert set(loaded.pack.localization.translations[locale].text) == expected
            metadata = loaded.pack.localization.locale_metadata[locale]
            assert metadata.method.value == "machine_assisted_prototype"
            assert metadata.review_status.value == "native_review_required"


@pytest.mark.parametrize("service_id", ["uidai-aadhaar-address-update", "kerala-ign-oap"])
@pytest.mark.anyio
async def test_locales_change_words_but_not_procedure_semantics(client: AsyncClient, service_id: str) -> None:
    payloads = {}
    for locale in ("en", "hi", "ml"):
        response = await client.get(f"/api/v1/procedures/{service_id}?locale={locale}")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        payloads[locale] = response.json()
        assert payloads[locale]["locale"] == locale
    assert len({payloads[locale]["title"] for locale in payloads}) == 3
    invariant = lambda item: (
        item["service_id"], item["category"], item["official_handoff_url"], item["pack_version"],
        item["pack_digest"], item["fee"]["verification_status"], item["fee"]["amount"],
        [(claim["amount"], claim["currency"], tuple(claim["source_ids"])) for claim in item["fee"]["claims"]],
        [(source["source_id"], source["url"]) for source in item["sources"]],
    )
    assert invariant(payloads["en"]) == invariant(payloads["hi"]) == invariant(payloads["ml"])


@pytest.mark.anyio
async def test_unsupported_locale_is_rejected_safely(client: AsyncClient) -> None:
    response = await client.get("/api/v1/procedures?locale=fr")
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"error": "Invalid request"}


@pytest.mark.anyio
async def test_api_fails_safely_when_registry_is_unavailable(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_module, "procedure_registry", None)
    for path in ("/api/v1/procedures", "/api/v1/procedures/uidai-aadhaar-address-update"):
        response = await client.get(path)
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {"error": "Procedure guidance is unavailable"}

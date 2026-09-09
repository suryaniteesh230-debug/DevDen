from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from sahayi_api.assistance import build_personalized_checklist, prepare_synthetic_form_assistance
from sahayi_api.main import app
from sahayi_api.procedures import default_pack_root, load_procedure_registry


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as api_client:
        yield api_client


def test_active_assistance_metadata_is_strict_sourced_and_versioned() -> None:
    registry = load_procedure_registry(default_pack_root())
    aadhaar = registry["uidai-aadhaar-address-update"]
    kerala = registry["kerala-ign-oap"]
    assert aadhaar.pack.pack_version == "1.5.0"
    assert kerala.pack.pack_version == "1.3.0"
    assert aadhaar.pack.assistance.form_mode == "preparation_worksheet"
    assert aadhaar.pack.assistance.form_source_ids == []
    assert kerala.pack.assistance.form_mode == "official_form_worksheet"
    assert kerala.pack.assistance.form_source_ids == ["kerala-ign-oap-application-form"]
    assert all(field.source_ids for loaded in registry.values() for field in loaded.pack.assistance.preparation_fields)


@pytest.mark.parametrize("locale", ["en", "hi", "ml"])
def test_checklist_is_localized_cited_and_preserves_sensitive_fact_handling(locale: str) -> None:
    loaded = load_procedure_registry(default_pack_root())["uidai-aadhaar-address-update"]
    checklist = build_personalized_checklist(
        loaded,
        {"mobile-auth-access": True, "address-update-route": "own-document", "accepted-poa-ready": True},
        locale=locale,
    )
    assert checklist.result.item_id == "result-own-document-ready"
    assert checklist.sources
    assert checklist.documents
    assert checklist.steps
    assert checklist.where
    assert checklist.not_verified
    assert any(item.item_id == "confirm-fee" for item in checklist.confirm)
    assert "50.00" not in checklist.confirm[-1].text
    assert "75.00" not in checklist.confirm[-1].text
    assert str(checklist.official_handoff_url).startswith("https://")


def test_kerala_checklist_is_preliminary_and_omits_pension_amount() -> None:
    loaded = load_procedure_registry(default_pack_root())["kerala-ign-oap"]
    checklist = build_personalized_checklist(loaded, {"age-60-or-higher": "no"})
    serialized = checklist.model_dump_json()
    assert checklist.result.item_id == "result-age-preliminary-mismatch"
    assert "approval" in serialized.lower()
    assert "2000" not in serialized
    assert any(item.item_id == "confirm-fee" for item in checklist.confirm)


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ({"mobile-auth-access": True, "address-update-route": "own-document", "accepted-poa-ready": True}, "result-own-document-ready"),
        ({"mobile-auth-access": True, "address-update-route": "head-of-family", "hof-participation-ready": True}, "result-hof-ready"),
        ({"mobile-auth-access": False}, "result-use-alternative-channel"),
        ({"mobile-auth-access": True, "address-update-route": "unsure"}, "result-route-cannot-confirm"),
    ],
)
def test_aadhaar_checklist_paths(answers: dict[str, object], expected: str) -> None:
    loaded = load_procedure_registry(default_pack_root())["uidai-aadhaar-address-update"]
    checklist = build_personalized_checklist(loaded, answers)
    assert checklist.result.item_id == expected
    assert all(item.item_id.startswith("personalized-step-") for item in checklist.steps)
    if expected == "result-use-alternative-channel":
        assert str(checklist.official_handoff_url).endswith("/en/enrolment-and-update")
        assert "centre" in checklist.where[0].text.lower()


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ({"age-60-or-higher": "no"}, "result-age-preliminary-mismatch"),
        ({"age-60-or-higher": "yes", "kerala-residence-three-years": "yes", "family-income-category": "prefer-not-to-answer"}, "result-more-information-needed"),
        ({"age-60-or-higher": "yes", "kerala-residence-three-years": "yes", "family-income-category": "within", "service-or-family-pension": "yes"}, "result-pension-local-body-review"),
        ({"age-60-or-higher": "yes", "kerala-residence-three-years": "yes", "family-income-category": "within", "service-or-family-pension": "no", "income-tax-payer": "no", "other-social-welfare-pension": "no"}, "result-preliminary-conditions-aligned"),
    ],
)
def test_kerala_checklist_paths(answers: dict[str, object], expected: str) -> None:
    loaded = load_procedure_registry(default_pack_root())["kerala-ign-oap"]
    checklist = build_personalized_checklist(loaded, answers)
    assert checklist.result.item_id == expected
    assert "2000" not in checklist.model_dump_json()
    assert any(item.item_id == "confirm-respectful-personal-circumstances-review" for item in checklist.confirm)


@pytest.mark.parametrize("service_id", ["uidai-aadhaar-address-update", "kerala-ign-oap"])
@pytest.mark.parametrize("locale", ["en", "hi", "ml"])
def test_synthetic_form_is_watermarked_and_never_prefills_private_fields(service_id: str, locale: str) -> None:
    loaded = load_procedure_registry(default_pack_root())[service_id]
    worksheet = prepare_synthetic_form_assistance(loaded, locale=locale)
    assert worksheet.persona.synthetic is True
    assert worksheet.persona.display_name.startswith("DEMO")
    assert worksheet.persona.readiness_answers
    assert worksheet.available_personas
    assert worksheet.sources
    assert worksheet.watermark
    if locale == "en":
        assert worksheet.watermark == "DEMO — NOT FOR SUBMISSION"
    assert all(field.value is None for field in worksheet.fields if field.handling != "fictional_demo")
    assert all(field.value is not None for field in worksheet.fields if field.handling == "fictional_demo")
    serialized = worksheet.model_dump_json()
    assert "1234 5678 9012" not in serialized
    assert "@" not in serialized


@pytest.mark.anyio
async def test_deterministic_assistance_endpoints_are_no_store(client: AsyncClient) -> None:
    checklist = await client.post(
        "/api/v1/procedures/uidai-aadhaar-address-update/checklist?locale=hi",
        json={"answers": {"mobile-auth-access": False}},
    )
    assert checklist.status_code == 200
    assert checklist.headers["cache-control"] == "no-store"
    assert checklist.json()["locale"] == "hi"
    worksheet = await client.post(
        "/api/v1/procedures/kerala-ign-oap/synthetic-form-assistance?locale=ml",
        json={"persona_id": None},
    )
    assert worksheet.status_code == 200
    assert worksheet.headers["cache-control"] == "no-store"
    assert worksheet.json()["mode"] == "official_form_worksheet"

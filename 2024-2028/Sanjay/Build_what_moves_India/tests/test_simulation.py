from __future__ import annotations

import re

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from sahayi_api.main import app
from sahayi_api.procedures import default_pack_root, load_procedure_registry
from sahayi_api.simulation import (
    DemoScenarioId,
    DemoStatusId,
    DemoStatusRequest,
    DemoSubmissionRequest,
    get_demo_status,
    start_demo_submission,
)


REGISTRY = load_procedure_registry(default_pack_root())


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.parametrize("service_id", ["uidai-aadhaar-address-update", "kerala-ign-oap"])
@pytest.mark.parametrize("locale", ["en", "hi", "ml"])
def test_demo_submission_is_strict_synthetic_localized_and_stateless(service_id: str, locale: str) -> None:
    loaded = REGISTRY[service_id]
    persona = loaded.pack.assistance.personas[0]
    request = DemoSubmissionRequest(persona_id=persona.persona_id, scenario_id="normal-completion")
    journey = start_demo_submission(loaded, request, locale=locale)
    assert journey.synthetic is True
    assert re.fullmatch(r"DEMO-[A-Z]+-[A-Z]+", journey.demo_reference)
    assert not re.search(r"\d", journey.demo_reference)
    assert journey.current_status_id == "preparation-completed"
    assert [item.status_id for item in journey.statuses] == [
        "preparation-completed",
        "demo-submitted",
        "simulated-review",
        "demo-completed",
    ]
    assert [item.state for item in journey.statuses] == ["current", "upcoming", "upcoming", "upcoming"]
    assert "SIMULATED" in journey.statuses[0].simulated_time_label or locale != "en"


def test_action_required_scenario_advances_deliberately() -> None:
    loaded = REGISTRY["uidai-aadhaar-address-update"]
    persona_id = loaded.pack.assistance.personas[0].persona_id
    started = start_demo_submission(
        loaded,
        DemoSubmissionRequest(persona_id=persona_id, scenario_id=DemoScenarioId.ACTION_REQUIRED),
    )
    action = get_demo_status(
        loaded,
        DemoStatusRequest(
            persona_id=persona_id,
            scenario_id=DemoScenarioId.ACTION_REQUIRED,
            demo_reference=started.demo_reference,
            status_id=DemoStatusId.ACTION_REQUIRED,
        ),
    )
    assert action.current_status_id == "action-required"
    assert [item.state for item in action.statuses] == ["complete", "complete", "complete", "current", "upcoming"]
    assert "official request" in next(item.explanation for item in action.statuses if item.state == "current")


def test_real_looking_or_mismatched_references_and_unknown_personas_are_rejected() -> None:
    loaded = REGISTRY["kerala-ign-oap"]
    persona_id = loaded.pack.assistance.personas[0].persona_id
    with pytest.raises(ValidationError):
        DemoStatusRequest(
            persona_id=persona_id,
            scenario_id="normal-completion",
            demo_reference="123456789012",
            status_id="demo-submitted",
        )
    with pytest.raises(ValueError, match="Invalid synthetic reference"):
        get_demo_status(
            loaded,
            DemoStatusRequest(
                persona_id=persona_id,
                scenario_id="normal-completion",
                demo_reference="DEMO-KERALA-ACTION",
                status_id="demo-submitted",
            ),
        )
    with pytest.raises(ValueError, match="Unknown synthetic persona"):
        start_demo_submission(loaded, DemoSubmissionRequest(persona_id="real-citizen", scenario_id="normal-completion"))


@pytest.mark.anyio
async def test_demo_endpoints_are_no_store_and_never_contact_government() -> None:
    loaded = REGISTRY["uidai-aadhaar-address-update"]
    persona_id = loaded.pack.assistance.personas[0].persona_id
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        started = await client.post(
            "/api/v1/procedures/uidai-aadhaar-address-update/demo-submission?locale=hi",
            json={"persona_id": persona_id, "scenario_id": "normal-completion"},
        )
        status = await client.post(
            "/api/v1/procedures/uidai-aadhaar-address-update/demo-status?locale=hi",
            json={
                "persona_id": persona_id,
                "scenario_id": "normal-completion",
                "demo_reference": started.json()["demo_reference"],
                "status_id": "demo-submitted",
            },
        )
    assert started.status_code == 200
    assert status.status_code == 200
    assert started.headers["cache-control"] == "no-store"
    assert status.headers["cache-control"] == "no-store"
    assert status.json()["current_status_id"] == "demo-submitted"

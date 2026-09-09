import pytest
from httpx import ASGITransport, AsyncClient

from sahayi_api.main import app
from sahayi_api.config import AGENT_MODEL, AGENT_PROVIDER, get_settings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as api_client:
        yield api_client


@pytest.mark.anyio
async def test_health_is_json_and_not_stored(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_public_config_has_no_secret_configuration(client: AsyncClient) -> None:
    response = await client.get("/api/v1/public-config")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "application_name": "Sahayi",
        "kiosk_mode": True,
        "agent_available": False,
        "agent_provider": AGENT_PROVIDER,
        "agent_model": AGENT_MODEL,
        "inactivity_timeout_seconds": 300,
        "inactivity_warning_seconds": 30,
    }
    assert response.json()["agent_model"] == "openai/gpt-oss-120b"
    serialized = response.text.lower()
    for prohibited in ("secret", "token", "password", "api_key", "origin", "environment"):
        assert prohibited not in serialized


def test_kiosk_timeout_configuration_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SAHAYI_KIOSK_INACTIVITY_SECONDS", "999999")
    monkeypatch.setenv("SAHAYI_KIOSK_WARNING_SECONDS", "1")
    configured = get_settings()
    assert configured.kiosk_inactivity_seconds == 1800
    assert configured.kiosk_warning_seconds == 10


@pytest.mark.anyio
async def test_cors_allows_only_configured_development_origin(client: AsyncClient) -> None:
    allowed = await client.get("/api/v1/health", headers={"Origin": "http://127.0.0.1:5173"})
    denied = await client.get("/api/v1/health", headers={"Origin": "https://example.test"})
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "access-control-allow-origin" not in denied.headers

    preflight = await client.options(
        "/api/v1/procedures/uidai-aadhaar-address-update/readiness/evaluate",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-methods"] == "GET, POST"

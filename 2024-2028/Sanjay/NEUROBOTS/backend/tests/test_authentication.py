import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import StaffRole
from app.core.exceptions import ClinicalApiError
from app.core.security import _secret_key, hash_password
from app.db.models import StaffUser
from tests.conftest import ApiClient


TEST_EMAIL = "staff@example.test"
TEST_PASSWORD = "correct horse battery staple"


def test_development_uses_stable_process_local_secret_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        auth_secret_key="",
        environment="development",
    )
    monkeypatch.setattr("app.core.security.get_settings", lambda: settings)
    _secret_key.cache_clear()
    try:
        first = _secret_key()
        assert len(first) >= 32
        assert _secret_key() == first
    finally:
        _secret_key.cache_clear()


def test_non_development_requires_configured_auth_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:pass@localhost/neurobots",
        auth_secret_key="",
        environment="production",
    )
    monkeypatch.setattr("app.core.security.get_settings", lambda: settings)
    _secret_key.cache_clear()
    try:
        with pytest.raises(ClinicalApiError) as raised:
            _secret_key()
        assert raised.value.code == "AUTH_NOT_CONFIGURED"
    finally:
        _secret_key.cache_clear()


def test_valid_staff_login_succeeds(client: ApiClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": TEST_EMAIL.upper(), "password": TEST_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] == 1800
    assert body["staff"]["email"] == TEST_EMAIL
    assert body["staff"]["role"] == "DOCTOR"


def test_incorrect_password_fails_with_generic_error(client: ApiClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": TEST_EMAIL, "password": "incorrect password"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == {
        "code": "INVALID_CREDENTIALS",
        "detail": "Invalid credentials",
    }


def test_password_shorter_than_eight_characters_is_rejected(client: ApiClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": TEST_EMAIL, "password": "short77"},
    )

    assert response.status_code == 422


def test_nonexistent_user_fails_with_generic_error(client: ApiClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "missing@example.test", "password": TEST_PASSWORD},
    )

    assert response.status_code == 401
    assert response.json()["error"]["detail"] == "Invalid credentials"


def test_disabled_staff_user_cannot_log_in(
    client: ApiClient, db_session: Session
) -> None:
    db_session.add(
        StaffUser(
            email="disabled@example.test",
            full_name="Disabled Clinician",
            password_hash=hash_password(TEST_PASSWORD),
            role=StaffRole.NURSE,
            is_active=True,
        )
    )
    db_session.commit()

    active_login = client.post(
        "/api/auth/login",
        json={"email": "disabled@example.test", "password": TEST_PASSWORD},
    )
    staff_user = db_session.scalar(
        select(StaffUser).where(StaffUser.email == "disabled@example.test")
    )
    assert staff_user is not None
    staff_user.is_active = False
    db_session.commit()

    response = client.post(
        "/api/auth/login",
        json={"email": "disabled@example.test", "password": TEST_PASSWORD},
    )
    disabled_client = ApiClient(
        {"Authorization": f"Bearer {active_login.json()['access_token']}"}
    )
    protected_response = disabled_client.get("/api/queue")

    assert active_login.status_code == 200
    assert response.status_code == 401
    assert response.json()["error"]["detail"] == "Invalid credentials"
    assert protected_response.status_code == 401


def test_protected_endpoint_without_authentication_returns_401(
    client: ApiClient,
) -> None:
    response = ApiClient().get("/api/queue")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_health_endpoint_remains_public(client: ApiClient) -> None:
    response = ApiClient().get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_protected_endpoint_with_staff_authentication_succeeds(
    client: ApiClient,
) -> None:
    response = client.get("/api/queue")

    assert response.status_code == 200
    assert response.json() == []


def test_password_hashes_are_never_exposed(
    client: ApiClient, db_session: Session
) -> None:
    login = client.post(
        "/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    current = client.get("/api/auth/me")
    stored_user = db_session.scalar(select(StaffUser).where(StaffUser.email == TEST_EMAIL))

    assert login.status_code == 200
    assert current.status_code == 200
    assert "password" not in login.text.lower()
    assert "password" not in current.text.lower()
    assert stored_user is not None
    assert stored_user.password_hash.startswith("$argon2")
    assert stored_user.password_hash != TEST_PASSWORD


def test_current_user_returns_authenticated_staff_member(client: ApiClient) -> None:
    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": response.json()["id"],
        "email": TEST_EMAIL,
        "full_name": "Test Clinician",
        "role": "DOCTOR",
        "is_active": True,
        "created_at": response.json()["created_at"],
    }

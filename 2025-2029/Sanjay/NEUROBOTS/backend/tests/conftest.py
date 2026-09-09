import asyncio
import os
from collections.abc import AsyncGenerator, Generator

import httpx
import pytest
from sqlalchemy.orm import Session, sessionmaker

# The automated suite must never call a live clinical reasoning provider, even
# when a developer shell contains a real ignored credential.
os.environ["GEMINI_API_KEY"] = ""
os.environ["NEUROBOTS_AUTH_SECRET_KEY"] = "test-only-auth-secret-key-at-least-32-characters"

from app.db.base import Base
from app.db.models import StaffUser
from app.db.session import build_engine, get_db
from app.core.enums import StaffRole
from app.core.security import hash_password
from app.main import app


class ApiClient:
    """Small synchronous facade over HTTPX's in-process ASGI transport."""

    def __init__(self, default_headers: dict[str, str] | None = None) -> None:
        self.default_headers = default_headers or {}

    def authenticate(self, access_token: str) -> None:
        self.default_headers["Authorization"] = f"Bearer {access_token}"

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        headers = {**self.default_headers, **kwargs.pop("headers", {})}

        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as async_client:
                return await async_client.request(method, path, headers=headers, **kwargs)

        return asyncio.run(send())

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self.request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs) -> httpx.Response:
        return self.request("PATCH", path, **kwargs)


@pytest.fixture
def test_session_factory(tmp_path):
    database_path = tmp_path / "test-neurobots.db"
    test_engine = build_engine(f"sqlite:///{database_path}")
    testing_session = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(test_engine)
    yield testing_session
    test_engine.dispose()


@pytest.fixture
def db_session(test_session_factory) -> Generator[Session, None, None]:
    with test_session_factory() as session:
        yield session


@pytest.fixture
def client(test_session_factory) -> Generator[ApiClient, None, None]:

    async def override_get_db() -> AsyncGenerator[Session, None]:
        with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with test_session_factory() as session:
        session.add(
            StaffUser(
                email="staff@example.test",
                full_name="Test Clinician",
                password_hash=hash_password("correct horse battery staple"),
                role=StaffRole.DOCTOR,
                is_active=True,
            )
        )
        session.commit()

    api_client = ApiClient()
    login = api_client.post(
        "/api/auth/login",
        json={
            "email": "staff@example.test",
            "password": "correct horse battery staple",
        },
    )
    assert login.status_code == 200
    api_client.authenticate(login.json()["access_token"])
    yield api_client
    app.dependency_overrides.clear()


@pytest.fixture
def patient_payload() -> dict:
    return {
        "external_patient_id": "HOSP-1001",
        "first_name": "Mira",
        "last_name": "Patel",
        "date_of_birth": "1978-04-18",
        "gender": "female",
        "phone_number": "555-0142",
    }


@pytest.fixture
def patient(client: ApiClient, patient_payload: dict) -> dict:
    response = client.post("/api/patients", json=patient_payload)
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def encounter(client: ApiClient, patient: dict) -> dict:
    response = client.post(
        f"/api/patients/{patient['id']}/encounters",
        json={
            "encounter_type": "emergency",
            "chief_complaint": "Chest pain",
        },
    )
    assert response.status_code == 201
    return response.json()

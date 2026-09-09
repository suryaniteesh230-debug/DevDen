import pytest

from app.core.config import Settings
from app.db.session import build_engine


def test_neon_database_url_selects_psycopg_driver(monkeypatch) -> None:
    monkeypatch.delenv("NEUROBOTS_DATABASE_URL", raising=False)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://staff:secret@db.example.test/nextcare?sslmode=require",
    )

    settings = Settings(_env_file=None)

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.database_url.endswith("?sslmode=require")


def test_postgres_engine_can_be_constructed_without_connecting() -> None:
    engine = build_engine(
        "postgresql+psycopg://staff:secret@db.example.test/nextcare"
    )
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_settings_can_read_root_env_before_backend_env(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("NEUROBOTS_GEMINI_API_KEY", raising=False)
    root_env = tmp_path / ".env"
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir()
    backend_env = backend_dir / ".env"

    root_env.write_text("GEMINI_API_KEY=root-key\n", encoding="utf-8")
    backend_env.write_text("", encoding="utf-8")

    settings = Settings(_env_file=(root_env, backend_env))

    assert settings.gemini_api_key.get_secret_value() == "root-key"


def test_production_rejects_local_sqlite_database(monkeypatch) -> None:
    monkeypatch.setenv("NEUROBOTS_ENVIRONMENT", "production")
    monkeypatch.delenv("NEUROBOTS_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="hosted Postgres URL"):
        Settings(_env_file=None)

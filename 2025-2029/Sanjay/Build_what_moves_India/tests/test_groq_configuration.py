from pathlib import Path

from sahayi_api.config import AGENT_MODEL, AGENT_PROVIDER, GROQ_BASE_URL, get_settings


ROOT = Path(__file__).resolve().parents[1]
SELECTED_MODEL = "openai/gpt-oss-120b"
RETIRED_MODEL = "llama-3.3-70b-versatile"


def test_selected_model_is_the_sole_runtime_allowlisted_model(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("SAHAYI_AGENT_MODEL", RETIRED_MODEL)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")

    settings = get_settings()

    assert AGENT_PROVIDER == "groq"
    assert AGENT_MODEL == SELECTED_MODEL
    assert settings.agent_model == SELECTED_MODEL
    assert settings.groq_api_key is None
    assert GROQ_BASE_URL == "https://api.groq.com/openai/v1"


def test_runtime_and_render_configuration_use_only_groq_credentials() -> None:
    config_source = (ROOT / "src/sahayi_api/config.py").read_text()
    env_example = (ROOT / ".env.example").read_text()
    render = (ROOT / "render.yaml").read_text()

    for content in (config_source, env_example, render):
        assert SELECTED_MODEL in content
        assert RETIRED_MODEL not in content
        assert "OPENAI_API_KEY" not in content

    credential_lines = [line for line in env_example.splitlines() if "API_KEY" in line]
    assert credential_lines == ["GROQ_API_KEY=replace-in-secret-manager"]
    assert "- key: GROQ_API_KEY\n        sync: false" in render
    assert "value: openai/gpt-oss-120b" in render


def test_retired_model_appears_only_in_labelled_history_or_migration_checks() -> None:
    active_runtime_files = [
        ROOT / "src/sahayi_api/config.py",
        ROOT / ".env.example",
        ROOT / "render.yaml",
        ROOT / "docs/architecture.md",
        ROOT / ".ai/ARCHITECTURE.md",
        ROOT / ".ai/ENVIRONMENT.md",
        ROOT / ".ai/DEPLOYMENT.md",
    ]
    assert all(RETIRED_MODEL not in path.read_text() for path in active_runtime_files)

    readme = (ROOT / "README.md").read_text()
    decisions = (ROOT / ".ai/DECISIONS.md").read_text()
    assert "retired `llama-3.3-70b-versatile`" in readme
    assert "Historical migration context" in decisions
    assert "retirement of `llama-3.3-70b-versatile`" in decisions

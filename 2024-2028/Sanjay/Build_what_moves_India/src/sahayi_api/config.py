from __future__ import annotations

import os
from dataclasses import dataclass


AGENT_PROVIDER = "groq"
AGENT_MODEL = "openai/gpt-oss-120b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


def _float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


@dataclass(frozen=True)
class Settings:
    dev_frontend_origin: str
    kiosk_inactivity_seconds: int
    kiosk_warning_seconds: int
    agent_enabled: bool
    agent_provider: str
    agent_model: str
    agent_configuration_valid: bool
    groq_api_key: str | None
    agent_timeout_seconds: float
    agent_max_output_tokens: int
    agent_max_tool_calls: int
    agent_max_rounds: int
    agent_concurrency: int
    agent_request_budget: int
    agent_rate_limit: int
    agent_rate_window_seconds: int


def get_settings() -> Settings:
    origin = os.getenv("SAHAYI_DEV_FRONTEND_ORIGIN", "http://127.0.0.1:5173")
    configured_provider = os.getenv("SAHAYI_AGENT_PROVIDER", AGENT_PROVIDER).strip().lower()
    configured_model = os.getenv("SAHAYI_AGENT_MODEL", AGENT_MODEL).strip()
    configured_key = os.getenv("GROQ_API_KEY")
    return Settings(
        dev_frontend_origin=origin.rstrip("/"),
        kiosk_inactivity_seconds=_integer("SAHAYI_KIOSK_INACTIVITY_SECONDS", 300, 60, 1800),
        kiosk_warning_seconds=_integer("SAHAYI_KIOSK_WARNING_SECONDS", 30, 10, 120),
        agent_enabled=_boolean("SAHAYI_AGENT_ENABLED", False),
        agent_provider=configured_provider if configured_provider == AGENT_PROVIDER else AGENT_PROVIDER,
        agent_model=configured_model if configured_model == AGENT_MODEL else AGENT_MODEL,
        agent_configuration_valid=configured_provider == AGENT_PROVIDER and configured_model == AGENT_MODEL,
        groq_api_key=configured_key.strip() if configured_key and configured_key.strip() else None,
        agent_timeout_seconds=_float("SAHAYI_AGENT_TIMEOUT_SECONDS", 8.0, 2.0, 20.0),
        agent_max_output_tokens=_integer("SAHAYI_AGENT_MAX_OUTPUT_TOKENS", 700, 256, 1200),
        agent_max_tool_calls=_integer("SAHAYI_AGENT_MAX_TOOL_CALLS", 6, 1, 8),
        agent_max_rounds=_integer("SAHAYI_AGENT_MAX_ROUNDS", 3, 1, 4),
        agent_concurrency=_integer("SAHAYI_AGENT_CONCURRENCY", 4, 1, 16),
        agent_request_budget=_integer("SAHAYI_AGENT_REQUEST_BUDGET", 200, 1, 10000),
        agent_rate_limit=_integer("SAHAYI_AGENT_RATE_LIMIT", 6, 1, 60),
        agent_rate_window_seconds=_integer("SAHAYI_AGENT_RATE_WINDOW_SECONDS", 60, 10, 300),
    )

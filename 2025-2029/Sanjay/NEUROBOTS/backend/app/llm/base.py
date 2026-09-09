from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


class LLMProviderError(RuntimeError):
    """Sanitized provider error safe for workflow traces and API responses."""


class LLMProviderUnavailableError(LLMProviderError):
    pass


class LLMTimeoutError(LLMProviderError):
    pass


class LLMRateLimitError(LLMProviderError):
    pass


class LLMResponseError(LLMProviderError):
    pass


class LLMStructuredOutputError(LLMResponseError):
    pass


@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(slots=True)
class ProviderTurn:
    provider: str
    model: str
    assistant_message: dict[str, Any]
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    structured_output: BaseModel | None = None
    latency_ms: float = 0.0


class LLMProvider(ABC):
    """Provider-neutral boundary used by clinical agents."""

    provider_name: str
    model: str

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def generate_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        output_schema: type[BaseModel],
        timeout_seconds: float,
    ) -> ProviderTurn: ...

    @abstractmethod
    def generate_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        output_schema: type[BaseModel],
        timeout_seconds: float,
    ) -> ProviderTurn: ...

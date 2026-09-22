from __future__ import annotations

import json
from functools import lru_cache
from time import perf_counter, sleep
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMResponseError,
    LLMStructuredOutputError,
    LLMTimeoutError,
    ProviderTurn,
    ToolCallRequest,
)


def _error_status_code(exception: Exception) -> int | None:
    for attribute in ("status_code", "status", "code"):
        value = getattr(exception, attribute, None)
        if isinstance(value, int):
            return value
    response = getattr(exception, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code
    return None


def _error_headers(exception: Exception) -> dict[str, str]:
    response = getattr(exception, "response", None)
    headers = getattr(response, "headers", None)
    if isinstance(headers, dict):
        return {str(key).casefold(): str(value) for key, value in headers.items()}
    if headers is not None and hasattr(headers, "items"):
        return {str(key).casefold(): str(value) for key, value in headers.items()}
    raw_headers = getattr(exception, "headers", None)
    if isinstance(raw_headers, dict):
        return {str(key).casefold(): str(value) for key, value in raw_headers.items()}
    return {}


def _retry_after_seconds(exception: Exception) -> str | None:
    return _error_headers(exception).get("retry-after")


def _is_timeout_error(exception: Exception) -> bool:
    name = type(exception).__name__.casefold()
    return "timeout" in name


def _is_connection_error(exception: Exception) -> bool:
    name = type(exception).__name__.casefold()
    return "connection" in name or "transport" in name


class GeminiProvider(LLMProvider):
    provider_name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_retries: int = 2,
        max_output_tokens: int = 4096,
        thinking_budget: int = 0,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self.model = model.strip() or "gemini-3.6-flash"
        self.max_retries = max_retries
        self.max_output_tokens = max_output_tokens
        self.thinking_budget = thinking_budget
        self._client = client

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    @property
    def client(self) -> Any:
        if not self.available:
            raise LLMProviderUnavailableError(
                "Gemini provider is unavailable: API key missing"
            )
        if self._client is None:
            try:
                from google import genai
            except ModuleNotFoundError as exception:
                raise LLMProviderUnavailableError(
                    "Gemini provider is unavailable: google-genai is not installed"
                ) from exception
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _invoke_with_retries(self, request: Any) -> Any:
        attempts = self.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                return request()
            except Exception as exception:
                status_code = _error_status_code(exception)
                retryable = status_code in {429, 500, 502, 503, 504} or _is_connection_error(
                    exception
                )
                if attempt >= attempts or not retryable:
                    raise
                retry_after = _retry_after_seconds(exception)
                if retry_after and retry_after.isdigit():
                    sleep_seconds = min(float(retry_after), 5.0)
                else:
                    sleep_seconds = min(0.5 * (2 ** (attempt - 1)), 2.0)
                sleep(sleep_seconds)

    def _build_contents(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        system_instruction: str | None = None
        contents: list[dict[str, Any]] = []
        for index, message in enumerate(messages):
            role = str(message.get("role", "user"))
            content = message.get("content")
            if role == "system":
                if index == 0 and isinstance(content, str):
                    system_instruction = content
                    continue
                role = "user"

            if role == "assistant":
                parts: list[dict[str, Any]] = []
                if isinstance(content, str) and content.strip():
                    parts.append({"text": content})
                for tool_call in message.get("tool_calls") or []:
                    function = tool_call.get("function") or {}
                    arguments = function.get("arguments", "{}")
                    try:
                        parsed_arguments = json.loads(arguments)
                    except json.JSONDecodeError as exception:
                        raise LLMResponseError(
                            "Stored tool-call arguments could not be translated for Gemini"
                        ) from exception
                    parts.append(
                        {
                            "function_call": {
                                "name": str(function.get("name", "")),
                                "args": parsed_arguments,
                            }
                        }
                    )
                contents.append({"role": "model", "parts": parts or [{"text": ""}]})
                continue

            if role == "tool":
                if isinstance(content, str) and content:
                    try:
                        response_payload = json.loads(content)
                    except json.JSONDecodeError:
                        response_payload = {"result": content}
                else:
                    response_payload = {"result": content}
                contents.append(
                    {
                        "role": "tool",
                        "parts": [
                            {
                                "function_response": {
                                    "name": str(message.get("name", "")),
                                    "response": response_payload,
                                }
                            }
                        ],
                    }
                )
                continue

            text = "" if content is None else str(content)
            contents.append({"role": "user", "parts": [{"text": text}]})
        return system_instruction, contents

    def _build_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        declarations = []
        for tool in tools:
            function = tool.get("function") or {}
            declarations.append(
                {
                    "name": str(function.get("name", "")),
                    "description": str(function.get("description", "")),
                    "parameters_json_schema": function.get("parameters", {"type": "object"}),
                }
            )
        return [{"function_declarations": declarations}] if declarations else []

    def _extract_text(self, response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            text_parts = [
                str(part.text).strip()
                for part in parts
                if getattr(part, "text", None) and str(part.text).strip()
            ]
            if text_parts:
                return "\n".join(text_parts)
        return ""

    def _extract_function_calls(self, response: Any) -> list[ToolCallRequest]:
        raw_calls = getattr(response, "function_calls", None)
        if raw_calls is None:
            raw_calls = []
            candidates = getattr(response, "candidates", None) or []
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                parts = getattr(content, "parts", None) or []
                for part in parts:
                    function_call = getattr(part, "function_call", None)
                    if function_call is not None:
                        raw_calls.append(function_call)

        tool_calls: list[ToolCallRequest] = []
        for index, call in enumerate(raw_calls, start=1):
            nested = getattr(call, "function_call", None)
            source = nested if nested is not None else call
            name = getattr(source, "name", None)
            arguments = getattr(source, "args", None)
            if name is None:
                name = getattr(call, "name", None)
            if arguments is None:
                arguments = getattr(call, "args", None)
            if not isinstance(arguments, dict):
                raise LLMResponseError("Gemini returned invalid tool arguments")
            tool_calls.append(
                ToolCallRequest(
                    id=str(getattr(call, "id", None) or f"gemini-call-{index}"),
                    name=str(name),
                    arguments=arguments,
                )
            )
        return tool_calls

    def _request(
        self,
        *,
        messages: list[dict[str, Any]],
        output_schema: type[BaseModel],
        timeout_seconds: float,
        tools: list[dict[str, Any]] | None,
    ) -> ProviderTurn:
        if not self.available:
            raise LLMProviderUnavailableError(
                "Gemini provider is unavailable: API key missing"
            )

        system_instruction, contents = self._build_contents(messages)
        config: dict[str, Any] = {
            "max_output_tokens": self.max_output_tokens,
            "http_options": {"timeout": timeout_seconds},
        }
        if system_instruction:
            config["system_instruction"] = system_instruction
        if self.thinking_budget >= -1:
            config["thinking_config"] = {"thinking_budget": self.thinking_budget}
        if tools:
            config["tools"] = self._build_tools(tools)
            config["automatic_function_calling"] = {"disable": True}
        else:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = output_schema.model_json_schema()

        timer = perf_counter()
        try:
            response = self._invoke_with_retries(
                lambda: self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
            )
        except LLMProviderError:
            raise
        except Exception as exception:
            status_code = _error_status_code(exception)
            retry_after = _retry_after_seconds(exception)
            if _is_timeout_error(exception):
                raise LLMTimeoutError("Gemini request timed out") from exception
            if status_code == 429:
                suffix = f"; retry after {retry_after} seconds" if retry_after else ""
                raise LLMRateLimitError(f"Gemini rate limit reached{suffix}") from exception
            if _is_connection_error(exception) or status_code in {500, 502, 503, 504}:
                raise LLMProviderError(
                    f"Gemini request failed ({type(exception).__name__})"
                ) from exception
            raise LLMProviderError(
                f"Gemini provider failed ({type(exception).__name__})"
            ) from exception

        latency_ms = round((perf_counter() - timer) * 1000, 3)
        actual_model = str(
            getattr(response, "model_version", None)
            or getattr(response, "model", None)
            or self.model
        )

        tool_calls = self._extract_function_calls(response)
        assistant_message: dict[str, Any] = {
            "role": "assistant",
            "content": self._extract_text(response) or None,
        }
        if tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, separators=(",", ":")),
                    },
                }
                for call in tool_calls
            ]

        structured_output: BaseModel | None = None
        if not tool_calls and not tools:
            content = self._extract_text(response)
            if not content:
                raise LLMResponseError("Gemini returned no structured content")
            try:
                structured_output = output_schema.model_validate_json(content)
            except (ValidationError, ValueError, TypeError) as exception:
                raise LLMStructuredOutputError(
                    "Gemini structured output failed validation"
                ) from exception

        return ProviderTurn(
            provider=self.provider_name,
            model=actual_model,
            assistant_message=assistant_message,
            tool_calls=tool_calls,
            structured_output=structured_output,
            latency_ms=latency_ms,
        )

    def generate_with_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        output_schema: type[BaseModel],
        timeout_seconds: float,
    ) -> ProviderTurn:
        return self._request(
            messages=messages,
            tools=tools,
            output_schema=output_schema,
            timeout_seconds=timeout_seconds,
        )

    def generate_structured(
        self,
        *,
        messages: list[dict[str, Any]],
        output_schema: type[BaseModel],
        timeout_seconds: float,
    ) -> ProviderTurn:
        return self._request(
            messages=messages,
            tools=None,
            output_schema=output_schema,
            timeout_seconds=timeout_seconds,
        )


@lru_cache(maxsize=1)
def get_gemini_provider() -> GeminiProvider:
    settings = get_settings()
    return GeminiProvider(
        api_key=settings.gemini_api_key.get_secret_value(),
        model=settings.gemini_model,
        max_retries=settings.gemini_max_retries,
        max_output_tokens=settings.gemini_max_output_tokens,
        thinking_budget=settings.gemini_thinking_budget,
    )

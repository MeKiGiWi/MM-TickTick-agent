from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List, Tuple

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

from app.domain.models import OpenRouterConfig
from app.tools.registry import ToolRegistry


@dataclass
class ChatCompletionResult:
    message: dict[str, Any]
    raw_response: dict[str, Any]


class OpenRouterError(RuntimeError):
    pass


class NetworkError(OpenRouterError):
    pass


class ProviderUnavailable(OpenRouterError):
    pass


class RateLimitExceeded(OpenRouterError):
    pass


class ConfigurationError(OpenRouterError):
    pass


class OpenRouterClient:
    NETWORK_RETRY_ATTEMPTS = 2

    def __init__(self, config: OpenRouterConfig) -> None:
        self.config = config
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=60.0,
        )

    def create_chat_completion(
        self,
        *,
        messages: List[dict[str, Any]],
        tools: List[dict[str, Any]],
    ) -> ChatCompletionResult:
        candidate_models = self._candidate_models()
        attempted: list[str] = []
        pending = list(candidate_models)

        while pending:
            model = pending.pop(0)
            attempted.append(model)
            try:
                response = self._create_chat_completion_for_model(
                    model=model, messages=messages, tools=tools
                )
                payload = self._dump_response(response)
                message = self._extract_message(payload)
                return ChatCompletionResult(message=message, raw_response=payload)
            except RateLimitExceeded as exc:
                if self._is_free_models_per_min_error(exc) and self._is_free_model(model):
                    pending = [
                        candidate for candidate in pending if not self._is_free_model(candidate)
                    ]
                if pending:
                    continue
                attempted_text = ", ".join(attempted)
                raise RateLimitExceeded(
                    f"OpenRouter rate limit: {exc}. Проверены модели: [{attempted_text}]"
                ) from exc
            except ProviderUnavailable as exc:
                pending = [candidate for candidate in pending if not self._is_free_model(candidate)]
                if pending:
                    continue
                attempted_text = ", ".join(attempted)
                raise ProviderUnavailable(
                    f"OpenRouter provider unavailable: {exc}. Проверены модели: [{attempted_text}]"
                ) from exc

        raise OpenRouterError("OpenRouter request failed without a response")

    def _create_chat_completion_for_model(
        self,
        *,
        model: str,
        messages: List[dict[str, Any]],
        tools: List[dict[str, Any]],
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.NETWORK_RETRY_ATTEMPTS):
            try:
                return self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    extra_body=self._build_extra_body(),
                )
            except (APIConnectionError, APITimeoutError) as exc:
                last_error = exc
                if attempt == self.NETWORK_RETRY_ATTEMPTS - 1:
                    raise NetworkError(
                        f"OpenRouter network error: {self._format_network_error(exc)}"
                    ) from exc
            except (RateLimitError, APIStatusError) as exc:
                raise self._classify_status_error(exc) from exc

        if last_error is not None:
            raise NetworkError(
                f"OpenRouter network error: {self._format_network_error(last_error)}"
            ) from last_error
        raise NetworkError("OpenRouter network error")

    def _candidate_models(self) -> list[str]:
        candidates = [self.config.model, *self.config.fallback_models]
        seen: set[str] = set()
        result: list[str] = []
        for model in candidates:
            normalized = model.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    def _build_extra_body(self) -> dict[str, Any] | None:
        body: dict[str, Any] = {}
        if self.config.reasoning_enabled:
            body["reasoning"] = {"enabled": True}
        return body or None

    @staticmethod
    def _dump_response(response: Any) -> dict[str, Any]:
        payload = response.model_dump(mode="json", exclude_none=True)
        if getattr(response, "model_extra", None):
            payload.update(response.model_extra)
        return payload

    @staticmethod
    def _extract_message(payload: dict[str, Any]) -> dict[str, Any]:
        choice = (payload.get("choices") or [{}])[0]
        message = dict(choice.get("message") or {})
        if not message:
            raise ValueError("OpenRouter response does not contain a message")
        return message

    @staticmethod
    def _format_network_error(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        lowered = message.lower()
        if "name or service not known" in lowered or "nodename nor servname provided" in lowered:
            return "ошибка DNS-разрешения имени"
        if "temporary failure in name resolution" in lowered:
            return "временная ошибка DNS-разрешения имени"
        if "timed out" in lowered:
            return "таймаут соединения"
        return message

    def _classify_status_error(self, exc: Exception) -> OpenRouterError:
        message = self._format_status_error(exc)
        lowered = message.lower()
        status_code = getattr(exc, "status_code", None)

        if status_code == 429 or isinstance(exc, RateLimitError):
            if "free-models-per-min" in lowered:
                return RateLimitExceeded(
                    "достигнут лимит free-models-per-min; повторите позже или настройте платную fallback-модель"
                )
            return RateLimitExceeded(f"слишком много запросов: {message}")

        if status_code == 503 and "no healthy upstream" in lowered:
            return ProviderUnavailable(
                "no healthy upstream; попробую платную fallback-модель, если она настроена"
            )

        if status_code in {400, 401, 403, 404}:
            return ConfigurationError(f"ошибка конфигурации OpenRouter: {message}")

        return OpenRouterError(f"OpenRouter request failed: {message}")

    @staticmethod
    def _is_free_model(model: str) -> bool:
        normalized = model.strip().lower()
        return normalized.endswith(":free") or normalized.endswith("/free")

    @staticmethod
    def _is_free_models_per_min_error(exc: Exception) -> bool:
        return "free-models-per-min" in str(exc).lower()

    @staticmethod
    def _format_status_error(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        status_code = getattr(exc, "status_code", None)
        if status_code:
            return f"{status_code}: {message}"
        return message


class OpenRouterToolLoop:
    def __init__(
        self,
        client: OpenRouterClient,
        tool_registry: ToolRegistry,
        *,
        max_tool_steps: int = 4,
    ) -> None:
        self.client = client
        self.tool_registry = tool_registry
        self.max_tool_steps = max_tool_steps

    def run_turn(self, messages: List[dict[str, Any]]) -> Tuple[str, List[dict[str, Any]]]:
        tools = self.tool_registry.list_openrouter_tools()
        local_messages = list(messages)

        for _ in range(self.max_tool_steps):
            result = self.client.create_chat_completion(messages=local_messages, tools=tools)
            assistant_message = {
                "role": result.message.get("role") or "assistant",
                "content": result.message.get("content") or "",
            }
            if "tool_calls" in result.message:
                assistant_message["tool_calls"] = result.message["tool_calls"]
            if "reasoning_details" in result.message:
                assistant_message["reasoning_details"] = result.message["reasoning_details"]
            local_messages.append(assistant_message)

            tool_calls = result.message.get("tool_calls") or []
            if not tool_calls:
                content = str(assistant_message["content"]).strip()
                if content:
                    assistant_message["content"] = content
                    return content, local_messages
                raise RuntimeError(
                    "Не получил текстовый ответ от модели: пустой ответ без tool calls."
                )

            for tool_call in tool_calls:
                function = tool_call["function"]
                try:
                    content = self.tool_registry.execute_tool(
                        function["name"],
                        function.get("arguments", "{}"),
                    )
                except Exception as exc:
                    content = json.dumps(
                        {
                            "error": {
                                "tool": function["name"],
                                "message": str(exc),
                            }
                        },
                        ensure_ascii=False,
                    )
                local_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": function["name"],
                        "content": content,
                    }
                )

        raise RuntimeError("Не получил текстовый ответ от модели после tool calls.")

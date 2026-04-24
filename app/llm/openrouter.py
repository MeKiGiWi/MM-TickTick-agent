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


class _TryNextModel(Exception):
    def __init__(self, error: Exception) -> None:
        super().__init__(str(error))
        self.error = error


class OpenRouterClient:
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
        last_rate_limit_error: Exception | None = None
        candidate_models = self._candidate_models()
        for model_index, model in enumerate(candidate_models):
            try:
                response = self._create_chat_completion_for_model(
                    model=model,
                    fallback_models=candidate_models[model_index + 1 :],
                    messages=messages,
                    tools=tools,
                )
                payload = self._dump_response(response)
                message = self._extract_message(payload)
                return ChatCompletionResult(message=message, raw_response=payload)
            except _TryNextModel as exc:
                last_rate_limit_error = exc.error
                continue

        if last_rate_limit_error is not None:
            attempted = ", ".join(candidate_models)
            raise RuntimeError(
                "OpenRouter rate limit error after trying models "
                f"[{attempted}]: {self._format_status_error(last_rate_limit_error)}"
            ) from last_rate_limit_error
        raise RuntimeError("OpenRouter request failed without a response")

    def _create_chat_completion_for_model(
        self,
        *,
        model: str,
        fallback_models: list[str],
        messages: List[dict[str, Any]],
        tools: List[dict[str, Any]],
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                return self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    extra_body=self._build_extra_body(fallback_models),
                )
            except (APIConnectionError, APITimeoutError) as exc:
                last_error = exc
                if attempt == 2:
                    raise RuntimeError(
                        f"OpenRouter network error: {self._format_network_error(exc)}"
                    ) from exc
            except (RateLimitError, APIStatusError) as exc:
                if self._should_try_next_model(exc):
                    raise _TryNextModel(exc) from exc
                raise RuntimeError(
                    f"OpenRouter request failed: {self._format_status_error(exc)}"
                ) from exc

        if last_error is not None:
            raise RuntimeError(
                f"OpenRouter network error: {self._format_network_error(last_error)}"
            ) from last_error
        raise RuntimeError("OpenRouter network error")

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

    def _build_extra_body(self, fallback_models: list[str] | None = None) -> dict[str, Any] | None:
        body: dict[str, Any] = {}
        if self.config.reasoning_enabled:
            body["reasoning"] = {"enabled": True}
        if fallback_models:
            body["models"] = fallback_models
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

    @staticmethod
    def _should_try_next_model(exc: Exception) -> bool:
        if isinstance(exc, RateLimitError):
            return True
        status_code = getattr(exc, "status_code", None)
        if status_code == 429:
            return True
        message = str(exc).lower()
        return "rate limit" in message or "rate-limited" in message or "429" in message

    @staticmethod
    def _format_status_error(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        status_code = getattr(exc, "status_code", None)
        if status_code:
            return f"{status_code}: {message}"
        return message


class OpenRouterToolLoop:
    def __init__(self, client: OpenRouterClient, tool_registry: ToolRegistry) -> None:
        self.client = client
        self.tool_registry = tool_registry

    def run_turn(self, messages: List[dict[str, Any]]) -> Tuple[str, List[dict[str, Any]]]:
        tools = self.tool_registry.list_openrouter_tools()
        local_messages = list(messages)

        for _ in range(6):
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
                continue

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

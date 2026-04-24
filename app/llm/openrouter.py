from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List, Tuple

from openai import OpenAI

from app.domain.models import OpenRouterConfig
from app.tools.registry import ToolRegistry


@dataclass
class ChatCompletionResult:
    message: dict[str, Any]
    raw_response: dict[str, Any]


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
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            extra_body=self._build_extra_body(),
        )
        payload = self._dump_response(response)
        message = self._extract_message(payload)
        return ChatCompletionResult(message=message, raw_response=payload)

    def _build_extra_body(self) -> dict[str, Any] | None:
        if not self.config.reasoning_enabled:
            return None
        return {"reasoning": {"enabled": True}}

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

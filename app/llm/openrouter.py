from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, List, Tuple

import httpx

from app.domain.models import OpenRouterConfig
from app.tools.registry import ToolRegistry


@dataclass
class ChatCompletionResult:
    message: dict[str, Any]
    raw_response: dict[str, Any]


class OpenRouterClient:
    def __init__(self, config: OpenRouterConfig) -> None:
        self.config = config
        self.client = httpx.Client(
            base_url=config.base_url,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    def create_chat_completion(
        self,
        *,
        messages: List[dict[str, Any]],
        tools: List[dict[str, Any]],
    ) -> ChatCompletionResult:
        response = self.client.post(
            "/chat/completions",
            json={
                "model": self.config.model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
            },
        )
        response.raise_for_status()
        payload = response.json()
        message = payload["choices"][0]["message"]
        return ChatCompletionResult(message=message, raw_response=payload)


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
                "role": "assistant",
                "content": result.message.get("content") or "",
            }
            if "tool_calls" in result.message:
                assistant_message["tool_calls"] = result.message["tool_calls"]
            local_messages.append(assistant_message)

            tool_calls = result.message.get("tool_calls") or []
            if not tool_calls:
                return assistant_message["content"], local_messages

            for tool_call in tool_calls:
                function = tool_call["function"]
                try:
                    content = self.tool_registry.execute_tool(
                        function["name"],
                        function.get("arguments", "{}"),
                    )
                except Exception as exc:
                    content = json.dumps({"error": str(exc)}, ensure_ascii=False)
                local_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": function["name"],
                        "content": content,
                    }
                )

        raise RuntimeError("Tool loop exceeded maximum iterations")

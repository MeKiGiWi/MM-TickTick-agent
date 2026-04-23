from __future__ import annotations

from typing import Any

from app.llm.openrouter import ChatCompletionResult, OpenRouterToolLoop
from app.providers.mock.ticktick import MockTickTickProvider
from app.tools.registry import ToolRegistry


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def create_chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        self.calls += 1
        if self.calls == 1:
            return ChatCompletionResult(
                message={
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "list_tasks",
                                "arguments": "{}",
                            },
                        }
                    ],
                },
                raw_response={},
            )
        return ChatCompletionResult(
            message={"role": "assistant", "content": "Нашел задачи и готов помочь."},
            raw_response={},
        )


def test_tool_loop_executes_tool_then_returns_answer() -> None:
    loop = OpenRouterToolLoop(FakeClient(), ToolRegistry(MockTickTickProvider()))
    answer, messages = loop.run_turn([{"role": "user", "content": "покажи задачи"}])
    assert answer == "Нашел задачи и готов помочь."
    assert any(message["role"] == "tool" for message in messages)

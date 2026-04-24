from __future__ import annotations

from typing import Any

from app.llm.openrouter import ChatCompletionResult, OpenRouterToolLoop
from app.providers.mock.ticktick import MockTickTickProvider
from app.tools.registry import ToolRegistry


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0
        self.recorded_messages: list[list[dict[str, Any]]] = []

    def create_chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        self.calls += 1
        self.recorded_messages.append(messages)
        if self.calls == 1:
            return ChatCompletionResult(
                message={
                    "role": "assistant",
                    "content": "",
                    "reasoning_details": [
                        {"type": "reasoning.summary", "text": "Need to inspect tasks first."}
                    ],
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
                raw_response={"model": "openrouter/auto-picked"},
            )
        return ChatCompletionResult(
            message={"role": "assistant", "content": "Нашел задачи и готов помочь."},
            raw_response={"model": "openrouter/auto-picked"},
        )


def test_tool_loop_executes_tool_then_returns_answer() -> None:
    client = FakeClient()
    loop = OpenRouterToolLoop(client, ToolRegistry(MockTickTickProvider()))
    answer, messages = loop.run_turn([{"role": "user", "content": "покажи задачи"}])
    assert answer == "Нашел задачи и готов помочь."
    assert any(message["role"] == "tool" for message in messages)
    assistant_messages = [message for message in messages if message["role"] == "assistant"]
    assert assistant_messages[0]["reasoning_details"] == [
        {"type": "reasoning.summary", "text": "Need to inspect tasks first."}
    ]
    assert client.recorded_messages[1][1]["reasoning_details"] == [
        {"type": "reasoning.summary", "text": "Need to inspect tasks first."}
    ]


class ErrorAwareClient:
    def __init__(self) -> None:
        self.calls = 0
        self.tool_messages: list[dict[str, Any]] = []

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
                                "name": "get_task_details",
                                "arguments": '{"task_id":"missing"}',
                            },
                        }
                    ],
                },
                raw_response={"model": "openrouter/auto-picked"},
            )
        self.tool_messages = [message for message in messages if message["role"] == "tool"]
        return ChatCompletionResult(
            message={
                "role": "assistant",
                "content": "Не удалось получить задачу: tool вернул ошибку.",
            },
            raw_response={"model": "openrouter/auto-picked"},
        )


def test_tool_loop_preserves_structured_tool_errors() -> None:
    client = ErrorAwareClient()
    loop = OpenRouterToolLoop(client, ToolRegistry(MockTickTickProvider()))
    answer, messages = loop.run_turn([{"role": "user", "content": "покажи missing task"}])
    assert answer == "Не удалось получить задачу: tool вернул ошибку."
    assert client.tool_messages
    assert '"error"' in client.tool_messages[0]["content"]
    assert '"message"' in client.tool_messages[0]["content"]


class WhitespaceContentClient:
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
                message={"role": "assistant", "content": "\n\nГотово"},
                raw_response={"model": "openrouter/auto-picked"},
            )
        raise AssertionError("unexpected extra call")


def test_tool_loop_strips_leading_newlines_from_answer() -> None:
    loop = OpenRouterToolLoop(WhitespaceContentClient(), ToolRegistry(MockTickTickProvider()))
    answer, _messages = loop.run_turn([{"role": "user", "content": "ok"}])
    assert answer == "Готово"


class EmptyContentClient:
    def __init__(self) -> None:
        self.calls = 0

    def create_chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        self.calls += 1
        return ChatCompletionResult(
            message={"role": "assistant", "content": "   "},
            raw_response={"model": "openrouter/auto-picked"},
        )


def test_tool_loop_raises_helpful_error_for_empty_answer() -> None:
    loop = OpenRouterToolLoop(EmptyContentClient(), ToolRegistry(MockTickTickProvider()))
    try:
        loop.run_turn([{"role": "user", "content": "ok"}])
    except RuntimeError as exc:
        assert "Не получил текстовый ответ от модели" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


class MultiStepClient:
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
                            "function": {"name": "create_task", "arguments": '{"title":"Parent"}'},
                        }
                    ],
                },
                raw_response={"model": "openrouter/auto-picked"},
            )
        if self.calls == 2:
            parent_id = next(message for message in messages if message["role"] == "tool")[
                "content"
            ]
            assert '"title": "Parent"' in parent_id
            return ChatCompletionResult(
                message={
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-2",
                            "type": "function",
                            "function": {
                                "name": "create_subtasks",
                                "arguments": '{"task_id":"task-101","titles":["A","B"]}',
                            },
                        }
                    ],
                },
                raw_response={"model": "openrouter/auto-picked"},
            )
        return ChatCompletionResult(
            message={"role": "assistant", "content": "Создал задачу и подзадачи."},
            raw_response={"model": "openrouter/auto-picked"},
        )


def test_tool_loop_supports_multi_step_tool_flow() -> None:
    loop = OpenRouterToolLoop(
        MultiStepClient(),
        ToolRegistry(MockTickTickProvider()),
        max_tool_steps=4,
    )
    answer, messages = loop.run_turn([{"role": "user", "content": "создай задачу с подзадачами"}])
    assert answer == "Создал задачу и подзадачи."
    assert len([message for message in messages if message["role"] == "tool"]) == 2


class CompositeToolClient:
    def create_chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        if len(messages) == 1:
            return ChatCompletionResult(
                message={
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "create_task_with_subtasks",
                                "arguments": '{"title":"Поездка","subtask_titles":["Билеты","Отель"]}',
                            },
                        }
                    ],
                },
                raw_response={"model": "openrouter/auto-picked"},
            )
        return ChatCompletionResult(
            message={"role": "assistant", "content": "Создал задачу с подзадачами."},
            raw_response={"model": "openrouter/auto-picked"},
        )


def test_tool_loop_supports_composite_tool_flow() -> None:
    loop = OpenRouterToolLoop(
        CompositeToolClient(),
        ToolRegistry(MockTickTickProvider()),
    )
    answer, messages = loop.run_turn([{"role": "user", "content": "создай задачу и подзадачи"}])
    assert answer == "Создал задачу с подзадачами."
    tool_messages = [message for message in messages if message["role"] == "tool"]
    assert len(tool_messages) == 1
    assert '"subtasks"' in tool_messages[0]["content"]

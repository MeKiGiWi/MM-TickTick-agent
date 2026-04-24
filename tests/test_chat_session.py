from types import SimpleNamespace

from app.chat.session import ChatSession
from app.providers.mock.ticktick import MockTickTickProvider
from app.tools.registry import ToolRegistry


def test_chat_session_sanitizes_surrogate_text() -> None:
    broken = "Привет \udcd1"
    cleaned = ChatSession._sanitize_text(broken)
    assert cleaned == "Привет �"


def test_chat_session_sanitizes_nested_messages() -> None:
    payload = [
        {"role": "user", "content": "hello \udcd1"},
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "1", "function": {"name": "x", "arguments": '{"q":"bad \udcd1"}'}}
            ],
        },
    ]
    cleaned = ChatSession._sanitize_payload(payload)
    assert cleaned[0]["content"] == "hello �"
    assert cleaned[1]["tool_calls"][0]["function"]["arguments"] == '{"q":"bad �"}'


def test_chat_session_adds_runtime_context() -> None:
    messages = [{"role": "system", "content": "base"}]
    updated = ChatSession._upsert_runtime_context(messages, user_timezone="Europe/Moscow")
    runtime_messages = [
        message
        for message in updated
        if str(message.get("content", "")).startswith("Runtime context:")
    ]
    assert len(runtime_messages) == 1
    assert "Current local date is" in runtime_messages[0]["content"]
    assert "Timezone is Europe/Moscow." in runtime_messages[0]["content"]


def test_chat_session_replaces_old_runtime_context() -> None:
    messages = [
        {"role": "system", "content": "base"},
        {"role": "system", "content": "Runtime context: stale"},
    ]
    updated = ChatSession._upsert_runtime_context(messages, user_timezone="Europe/Moscow")
    runtime_messages = [
        message
        for message in updated
        if str(message.get("content", "")).startswith("Runtime context:")
    ]
    assert len(runtime_messages) == 1
    assert runtime_messages[0]["content"] != "Runtime context: stale"


def test_local_projects_command_prints_projects_and_does_not_touch_history(capsys) -> None:
    session = ChatSession.__new__(ChatSession)
    session.provider = MockTickTickProvider()
    session.registry = ToolRegistry(session.provider, user_timezone="Europe/Moscow")
    session.messages = [{"role": "system", "content": "base"}]

    handled = session._handle_local_command("/projects")

    assert handled is True
    assert session.messages == [{"role": "system", "content": "base"}]
    output = capsys.readouterr().out
    assert "Проекты:" in output
    assert "Inbox (inbox)" in output
    assert "Work (work)" in output


def test_chat_session_prints_blank_line_before_agent_answer(monkeypatch, capsys) -> None:
    session = ChatSession.__new__(ChatSession)
    session.provider = MockTickTickProvider()
    session.registry = ToolRegistry(session.provider, user_timezone="Europe/Moscow")
    session.llm = SimpleNamespace(
        run_turn=lambda messages: (
            "Ответ пользователю",
            messages + [{"role": "assistant", "content": "Ответ пользователю"}],
        )
    )
    session.config = SimpleNamespace(user_timezone="Europe/Moscow")
    session.messages = [{"role": "system", "content": "base"}]

    answers = iter(["привет", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    session.run()

    output = capsys.readouterr().out
    assert "\n\n🤖 agent> Ответ пользователю\n" in output


def test_chat_session_strips_answer_and_prints_fallback_for_empty(monkeypatch, capsys) -> None:
    session = ChatSession.__new__(ChatSession)
    session.provider = MockTickTickProvider()
    session.registry = ToolRegistry(session.provider, user_timezone="Europe/Moscow")
    session.llm = SimpleNamespace(
        run_turn=lambda messages: ("\n\n", messages + [{"role": "assistant", "content": "\n\n"}])
    )
    session.config = SimpleNamespace(user_timezone="Europe/Moscow")
    session.messages = [{"role": "system", "content": "base"}]

    answers = iter(["привет", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    session.run()

    output = capsys.readouterr().out
    assert "🤖 agent> Не получил текстовый ответ от модели." in output


def test_chat_session_uses_smiley_prompts(monkeypatch, capsys) -> None:
    session = ChatSession.__new__(ChatSession)
    session.provider = MockTickTickProvider()
    session.registry = ToolRegistry(session.provider, user_timezone="Europe/Moscow")
    session.llm = SimpleNamespace(
        run_turn=lambda messages: (
            "Ответ пользователю",
            messages + [{"role": "assistant", "content": "Ответ пользователю"}],
        )
    )
    session.config = SimpleNamespace(user_timezone="Europe/Moscow")
    session.messages = [{"role": "system", "content": "base"}]

    prompts: list[str] = []
    answers = iter(["привет", "exit"])

    def fake_input(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)

    session.run()

    assert prompts == ["🙂 you> ", "🙂 you> "]


def test_chat_session_does_not_inject_keyword_based_clarify_context(monkeypatch) -> None:
    recorded_messages: list[dict[str, object]] = []

    def fake_run_turn(messages: list[dict[str, object]]) -> tuple[str, list[dict[str, object]]]:
        recorded_messages.extend(messages)
        return "Ок", messages + [{"role": "assistant", "content": "Ок"}]

    session = ChatSession.__new__(ChatSession)
    session.provider = MockTickTickProvider()
    session.registry = ToolRegistry(session.provider, user_timezone="Europe/Moscow")
    session.llm = SimpleNamespace(run_turn=fake_run_turn)
    session.config = SimpleNamespace(user_timezone="Europe/Moscow")
    session.messages = [{"role": "system", "content": "base"}]

    answers = iter(["разбей задачу на подзадачи", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    session.run()

    assert any(message["role"] == "user" for message in recorded_messages)
    assert all(
        "Clarify Agent" not in str(message.get("content", "")) for message in recorded_messages
    )


def test_chat_session_formats_network_like_turn_errors() -> None:
    message = ChatSession._format_turn_error(
        RuntimeError("OpenRouter network error: ошибка DNS-разрешения имени")
    )
    assert "временной сетевой ошибки" in message
    assert "DNS" in message


def test_chat_session_prints_tool_debug_info_when_enabled(capsys) -> None:
    previous_messages = [
        {"role": "system", "content": "base"},
        {"role": "user", "content": "создай задачу"},
    ]
    updated_messages = previous_messages + [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "create_task",
                        "arguments": '{"title":"Привет мир"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "name": "create_task",
            "tool_call_id": "call-1",
            "content": '{"id":"task-1","title":"Привет мир"}',
        },
    ]
    session = ChatSession.__new__(ChatSession)
    session.debug_tool_flow = True

    session._print_tool_debug_info(previous_messages, updated_messages)

    output = capsys.readouterr().out
    assert "ℹ️ system> tool flow" in output
    assert "tool call: create_task" in output
    assert '"title": "Привет мир"' in output
    assert "tool result: create_task" in output
    assert '"id": "task-1"' in output


def test_chat_session_does_not_print_tool_debug_info_when_disabled(capsys) -> None:
    session = ChatSession.__new__(ChatSession)
    session.debug_tool_flow = False

    session._print_tool_debug_info(
        [{"role": "user", "content": "x"}],
        [{"role": "user", "content": "x"}],
    )

    output = capsys.readouterr().out
    assert output == ""

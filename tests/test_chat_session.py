from types import SimpleNamespace

from app.providers.mock.ticktick import MockTickTickProvider
from app.tools.registry import ToolRegistry
from app.chat.session import ChatSession


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
        message for message in updated if str(message.get("content", "")).startswith("Runtime context:")
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
        message for message in updated if str(message.get("content", "")).startswith("Runtime context:")
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
        run_turn=lambda messages: ("Ответ пользователю", messages + [{"role": "assistant", "content": "Ответ пользователю"}])
    )
    session.clarify_agent = SimpleNamespace(assess_tasks=lambda tasks: [])
    session.config = SimpleNamespace(user_timezone="Europe/Moscow")
    session.messages = [{"role": "system", "content": "base"}]
    session._maybe_add_clarify_context = lambda user_input: None

    answers = iter(["привет", "exit"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    session.run()

    output = capsys.readouterr().out
    assert "\n\nagent> Ответ пользователю\n" in output

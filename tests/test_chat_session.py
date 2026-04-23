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

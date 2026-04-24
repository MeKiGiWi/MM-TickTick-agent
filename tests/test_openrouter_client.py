from __future__ import annotations

from typing import Any

import httpx
import pytest
from openai import RateLimitError

from app.domain.models import OpenRouterConfig
from app.llm.openrouter import OpenRouterClient


class FakeResponse:
    model_extra: dict[str, Any] | None = None

    def __init__(self, content: str, model: str) -> None:
        self.content = content
        self.model = model

    def model_dump(self, mode: str = "json", exclude_none: bool = True) -> dict[str, Any]:
        return {
            "model": self.model,
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": self.content,
                    }
                }
            ],
        }


class FakeCompletionsAPI:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _rate_limit_error(message: str = "Provider returned error: temporarily rate-limited upstream") -> RateLimitError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(429, request=request)
    return RateLimitError(message, response=response, body=None)


def test_openrouter_client_tries_next_model_on_rate_limit() -> None:
    client = OpenRouterClient(
        OpenRouterConfig(
            api_key="test-key",
            model="qwen/qwen3-coder:free",
            fallback_models=["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"],
        )
    )
    fake_api = FakeCompletionsAPI(
        [
            _rate_limit_error(),
            FakeResponse("Готово", "openai/gpt-4o-mini"),
        ]
    )
    client.client = type(
        "FakeOpenAI",
        (),
        {"chat": type("FakeChat", (), {"completions": fake_api})()},
    )()

    result = client.create_chat_completion(messages=[{"role": "user", "content": "hello"}], tools=[])

    assert result.message["content"] == "Готово"
    assert [call["model"] for call in fake_api.calls] == [
        "qwen/qwen3-coder:free",
        "openai/gpt-4o-mini",
    ]
    assert fake_api.calls[0]["extra_body"] == {
        "reasoning": {"enabled": True},
        "models": ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet"],
    }
    assert fake_api.calls[1]["extra_body"] == {
        "reasoning": {"enabled": True},
        "models": ["anthropic/claude-3.5-sonnet"],
    }


def test_openrouter_client_reports_exhausted_rate_limit_chain() -> None:
    client = OpenRouterClient(
        OpenRouterConfig(
            api_key="test-key",
            model="qwen/qwen3-coder:free",
            fallback_models=["openai/gpt-4o-mini"],
        )
    )
    fake_api = FakeCompletionsAPI([_rate_limit_error("429 on primary"), _rate_limit_error("429 on fallback")])
    client.client = type(
        "FakeOpenAI",
        (),
        {"chat": type("FakeChat", (), {"completions": fake_api})()},
    )()

    with pytest.raises(RuntimeError) as exc_info:
        client.create_chat_completion(messages=[{"role": "user", "content": "hello"}], tools=[])

    message = str(exc_info.value)
    assert "rate limit error after trying models" in message
    assert "qwen/qwen3-coder:free" in message
    assert "openai/gpt-4o-mini" in message


def test_openrouter_client_builds_extra_body_without_reasoning_when_disabled() -> None:
    client = OpenRouterClient(
        OpenRouterConfig(
            api_key="test-key",
            model="openrouter/free",
            fallback_models=["openai/gpt-4o-mini"],
            reasoning_enabled=False,
        )
    )

    assert client._build_extra_body(["openai/gpt-4o-mini"]) == {
        "models": ["openai/gpt-4o-mini"]
    }

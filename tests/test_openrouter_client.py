from __future__ import annotations

from typing import Any

import httpx
import pytest
from openai import APIConnectionError, APIStatusError, RateLimitError

from app.domain.models import OpenRouterConfig
from app.llm.openrouter import OpenRouterClient, ProviderUnavailable, RateLimitExceeded


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


def _rate_limit_error(
    message: str = "Provider returned error: temporarily rate-limited upstream",
) -> RateLimitError:
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

    result = client.create_chat_completion(
        messages=[{"role": "user", "content": "hello"}], tools=[]
    )

    assert result.message["content"] == "Готово"
    assert [call["model"] for call in fake_api.calls] == [
        "qwen/qwen3-coder:free",
        "openai/gpt-4o-mini",
    ]
    assert fake_api.calls[0]["extra_body"] is None
    assert fake_api.calls[1]["extra_body"] is None


def test_openrouter_client_raises_clear_message_for_free_models_per_min_limit() -> None:
    client = OpenRouterClient(
        OpenRouterConfig(
            api_key="test-key",
            model="qwen/qwen3-coder:free",
            fallback_models=["openai/gpt-4o-mini"],
        )
    )
    fake_api = FakeCompletionsAPI(
        [
            _rate_limit_error("429 free-models-per-min exceeded"),
            FakeResponse("Платный fallback", "openai/gpt-4o-mini"),
        ]
    )
    client.client = type(
        "FakeOpenAI",
        (),
        {"chat": type("FakeChat", (), {"completions": fake_api})()},
    )()

    result = client.create_chat_completion(
        messages=[{"role": "user", "content": "hello"}], tools=[]
    )

    assert result.message["content"] == "Платный fallback"
    assert [call["model"] for call in fake_api.calls] == [
        "qwen/qwen3-coder:free",
        "openai/gpt-4o-mini",
    ]


def test_openrouter_client_raises_clear_message_when_only_free_models_hit_limit() -> None:
    client = OpenRouterClient(
        OpenRouterConfig(
            api_key="test-key",
            model="qwen/qwen3-coder:free",
            fallback_models=["deepseek/free"],
        )
    )
    fake_api = FakeCompletionsAPI([_rate_limit_error("429 free-models-per-min exceeded")])
    client.client = type(
        "FakeOpenAI",
        (),
        {"chat": type("FakeChat", (), {"completions": fake_api})()},
    )()

    with pytest.raises(RateLimitExceeded) as exc_info:
        client.create_chat_completion(messages=[{"role": "user", "content": "hello"}], tools=[])

    assert "free-models-per-min" in str(exc_info.value)
    assert [call["model"] for call in fake_api.calls] == ["qwen/qwen3-coder:free"]


def test_openrouter_client_tries_non_free_fallback_on_retryable_503() -> None:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    status_error = APIStatusError(
        "Provider returned error: no healthy upstream",
        response=httpx.Response(503, request=request),
        body=None,
    )
    client = OpenRouterClient(
        OpenRouterConfig(
            api_key="test-key",
            model="qwen/qwen3-coder:free",
            fallback_models=["openai/gpt-4o-mini"],
        )
    )
    fake_api = FakeCompletionsAPI(
        [status_error, FakeResponse("Готово после 503", "openai/gpt-4o-mini")]
    )
    client.client = type(
        "FakeOpenAI",
        (),
        {"chat": type("FakeChat", (), {"completions": fake_api})()},
    )()

    result = client.create_chat_completion(
        messages=[{"role": "user", "content": "hello"}], tools=[]
    )

    assert result.message["content"] == "Готово после 503"
    assert [call["model"] for call in fake_api.calls] == [
        "qwen/qwen3-coder:free",
        "openai/gpt-4o-mini",
    ]


def test_openrouter_client_raises_provider_unavailable_without_non_free_fallback() -> None:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    status_error = APIStatusError(
        "Provider returned error: no healthy upstream",
        response=httpx.Response(503, request=request),
        body=None,
    )
    client = OpenRouterClient(
        OpenRouterConfig(
            api_key="test-key",
            model="qwen/qwen3-coder:free",
            fallback_models=["deepseek/free"],
        )
    )
    fake_api = FakeCompletionsAPI([status_error])
    client.client = type(
        "FakeOpenAI",
        (),
        {"chat": type("FakeChat", (), {"completions": fake_api})()},
    )()

    with pytest.raises(ProviderUnavailable) as exc_info:
        client.create_chat_completion(messages=[{"role": "user", "content": "hello"}], tools=[])

    assert "no healthy upstream" in str(exc_info.value)


def test_openrouter_client_retries_network_error_once_then_recovers() -> None:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    client = OpenRouterClient(OpenRouterConfig(api_key="test-key", model="openrouter/free"))
    fake_api = FakeCompletionsAPI(
        [
            APIConnectionError(message="Temporary failure in name resolution", request=request),
            FakeResponse("После ретрая", "openrouter/free"),
        ]
    )
    client.client = type(
        "FakeOpenAI",
        (),
        {"chat": type("FakeChat", (), {"completions": fake_api})()},
    )()

    result = client.create_chat_completion(
        messages=[{"role": "user", "content": "hello"}], tools=[]
    )

    assert result.message["content"] == "После ретрая"
    assert len(fake_api.calls) == 2


def test_openrouter_client_builds_extra_body_without_reasoning_when_disabled() -> None:
    client = OpenRouterClient(
        OpenRouterConfig(
            api_key="test-key",
            model="openrouter/free",
            fallback_models=["openai/gpt-4o-mini"],
            reasoning_enabled=False,
        )
    )

    assert client._build_extra_body() is None


def test_openrouter_client_uses_reasoning_only_when_enabled() -> None:
    client = OpenRouterClient(
        OpenRouterConfig(
            api_key="test-key",
            model="openrouter/free",
            reasoning_enabled=True,
        )
    )

    assert client._build_extra_body() == {"reasoning": {"enabled": True}}


def test_openrouter_client_does_not_use_double_fallback() -> None:
    client = OpenRouterClient(
        OpenRouterConfig(
            api_key="test-key",
            model="qwen/qwen3-coder:free",
            fallback_models=["openai/gpt-4o-mini"],
        )
    )
    fake_api = FakeCompletionsAPI(
        [
            _rate_limit_error("429 free-models-per-min exceeded"),
            FakeResponse("Готово", "openai/gpt-4o-mini"),
        ]
    )
    client.client = type(
        "FakeOpenAI",
        (),
        {"chat": type("FakeChat", (), {"completions": fake_api})()},
    )()

    client.create_chat_completion(messages=[{"role": "user", "content": "hello"}], tools=[])

    assert all("models" not in (call.get("extra_body") or {}) for call in fake_api.calls)

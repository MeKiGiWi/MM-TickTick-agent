from pathlib import Path

from app.config.setup import ensure_config


def test_setup_creates_local_config(monkeypatch, tmp_path: Path) -> None:
    answers = iter(["or-test-key", "", "", "mock"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setenv("APP_TIMEZONE", "Europe/Moscow")
    config = ensure_config(tmp_path)
    assert config.openrouter.api_key == "or-test-key"
    assert config.openrouter.model == "qwen/qwen-turbo"
    assert config.openrouter.fallback_models == []
    assert config.ticktick.provider == "mock"
    assert config.user_timezone == "Europe/Moscow"
    assert (tmp_path / "config.local.json").exists()


def test_setup_prompts_for_openrouter_values_without_env_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    answers = iter(
        ["prompt-key", "qwen/qwen-turbo", "openai/gpt-4o-mini, openai/gpt-4o-mini", "mock"]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setenv("TZ", "Europe/Moscow")
    config = ensure_config(tmp_path)
    assert config.openrouter.api_key == "prompt-key"
    assert config.openrouter.model == "qwen/qwen-turbo"
    assert config.openrouter.fallback_models == ["openai/gpt-4o-mini"]
    assert config.user_timezone == "Europe/Moscow"

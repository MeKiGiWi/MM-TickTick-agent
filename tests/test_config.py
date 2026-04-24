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


def test_setup_uses_openrouter_env(monkeypatch, tmp_path: Path) -> None:
    answers = iter(["", "", "mock"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-openrouter-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "qwen/qwen-turbo")
    monkeypatch.setenv(
        "OPENROUTER_FALLBACK_MODELS",
        "openai/gpt-4o-mini, anthropic/claude-3.5-sonnet , openai/gpt-4o-mini",
    )
    monkeypatch.setenv("TZ", "Europe/Moscow")
    config = ensure_config(tmp_path)
    assert config.openrouter.api_key == "env-openrouter-key"
    assert config.openrouter.model == "qwen/qwen-turbo"
    assert config.openrouter.fallback_models == [
        "openai/gpt-4o-mini",
        "anthropic/claude-3.5-sonnet",
    ]
    assert config.user_timezone == "Europe/Moscow"

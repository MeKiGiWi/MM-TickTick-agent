from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.domain.models import AppConfig, OpenRouterConfig, TickTickCredentials
from app.providers.ticktick.oauth import run_oauth_login
from app.storage.config_store import ConfigStore


def _prompt(prompt: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    if value:
        return value
    return default or ""


def ensure_config(root: Path) -> AppConfig:
    store = ConfigStore(root)
    if store.exists():
        config = store.load()
        if config.ticktick.provider == "ticktick" and not config.ticktick.access_token:
            print("TickTick настроен без access token. Запускаю OAuth login.")
            oauth_result = run_oauth_login(config.ticktick)
            config.ticktick.access_token = oauth_result.access_token
            config.ticktick.auth_state = oauth_result.state
            store.save(config)
        return config

    print("Первый запуск. Нужен локальный setup.")
    api_key = _prompt("Вставьте OpenRouter API key")
    model = _prompt(
        "OpenRouter model",
        "meta-llama/llama-3.3-70b-instruct:free",
    )
    provider = _prompt("TickTick provider (mock/ticktick)", "mock")
    client_id = _prompt("TickTick client_id", "")
    client_secret = _prompt("TickTick client_secret", "")
    redirect_uri = _prompt("TickTick redirect_uri", "http://localhost:8765/callback")
    scope = _prompt("TickTick OAuth scope", "tasks:write tasks:read")
    inbox_project_id = _prompt("TickTick inbox_project_id", "inbox")

    config = AppConfig(
        openrouter=OpenRouterConfig(api_key=api_key, model=model),
        ticktick=TickTickCredentials(
            provider="ticktick" if provider == "ticktick" else "mock",
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            inbox_project_id=inbox_project_id,
        ),
    )
    if config.ticktick.provider == "ticktick":
        oauth_result = run_oauth_login(config.ticktick)
        config.ticktick.access_token = oauth_result.access_token
        config.ticktick.auth_state = oauth_result.state
    store.save(config)
    print(f"Конфиг сохранен в {store.path}")
    return config

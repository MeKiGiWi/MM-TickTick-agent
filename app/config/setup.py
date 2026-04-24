from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.domain.models import AppConfig, OpenRouterConfig, TickTickCredentials
from app.providers.ticktick.oauth import run_oauth_login
from app.storage.config_store import ConfigStore
from app.utils.timezone import configured_timezone_name


def _prompt(prompt: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    if value:
        return value
    return default or ""


def _prompt_choice(prompt: str, choices: set[str], default: str) -> str:
    while True:
        value = _prompt(prompt, default).lower()
        if value in choices:
            return value
        print(f"Введите один из вариантов: {', '.join(sorted(choices))}")


def _parse_csv_models(value: str) -> list[str]:
    seen: set[str] = set()
    models: list[str] = []
    for item in value.split(","):
        model = item.strip()
        if not model or model in seen:
            continue
        seen.add(model)
        models.append(model)
    return models


def _build_openrouter_config() -> OpenRouterConfig:
    env_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    env_model = os.getenv("OPENROUTER_MODEL", "").strip() or "qwen/qwen-turbo"
    env_fallback_models = os.getenv("OPENROUTER_FALLBACK_MODELS", "").strip()

    api_key = env_api_key or _prompt("OpenRouter API key")
    model = _prompt("OpenRouter model", env_model)
    fallback_models_raw = _prompt(
        "OpenRouter fallback models (comma-separated)",
        env_fallback_models,
    )
    return OpenRouterConfig(
        api_key=api_key,
        model=model,
        fallback_models=_parse_csv_models(fallback_models_raw),
    )


def _build_ticktick_credentials() -> TickTickCredentials:
    print()
    print("TickTick provider: ticktick")
    print("Для реального TickTick нужен TickTick Developer app с OAuth credentials.")
    print("Если часть значений уже есть в env, wizard подхватит их и спросит только недостающее.")

    env_defaults = {
        "client_id": os.getenv("TICKTICK_CLIENT_ID", "").strip(),
        "client_secret": os.getenv("TICKTICK_CLIENT_SECRET", "").strip(),
        "redirect_uri": os.getenv("TICKTICK_REDIRECT_URI", "").strip(),
        "scope": os.getenv("TICKTICK_SCOPE", "").strip() or "tasks:write tasks:read",
    }

    client_id = env_defaults["client_id"] or _prompt("TickTick client_id")
    client_secret = env_defaults["client_secret"] or _prompt("TickTick client_secret")
    redirect_uri = env_defaults["redirect_uri"] or _prompt(
        "TickTick redirect_uri",
        "http://localhost:8765/callback",
    )
    scope = env_defaults["scope"] or "tasks:write tasks:read"

    return TickTickCredentials(
        provider="ticktick",
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
    )


def _default_user_timezone() -> Optional[str]:
    configured = configured_timezone_name()
    if configured:
        return configured
    current = datetime.now().astimezone().tzinfo
    key = getattr(current, "key", None)
    if isinstance(key, str) and key:
        return key
    return None


def _prompt_ticktick_inbox_project_id(current_value: str = "inbox") -> str:
    print()
    print("OAuth завершен. Теперь можно настроить, куда складывать новые задачи.")
    return _prompt("TickTick inbox_project_id", current_value or "inbox")


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

    print("Первый запуск. Сохраняю локальный config для CLI.")
    openrouter_config = _build_openrouter_config()
    provider = _prompt_choice("TickTick provider (mock/ticktick)", {"mock", "ticktick"}, "mock")

    ticktick_config = (
        TickTickCredentials(provider="mock")
        if provider == "mock"
        else _build_ticktick_credentials()
    )
    config = AppConfig(
        openrouter=openrouter_config,
        ticktick=ticktick_config,
        user_timezone=_default_user_timezone(),
    )
    if config.ticktick.provider == "ticktick":
        oauth_result = run_oauth_login(config.ticktick)
        config.ticktick.access_token = oauth_result.access_token
        config.ticktick.auth_state = oauth_result.state
        config.ticktick.inbox_project_id = _prompt_ticktick_inbox_project_id(
            config.ticktick.inbox_project_id
        )
    store.save(config)
    print(f"Конфиг сохранен в {store.path}")
    return config

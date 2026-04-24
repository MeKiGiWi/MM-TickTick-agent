from __future__ import annotations

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
    api_key = _prompt("OpenRouter API key")
    model = _prompt("OpenRouter model", "qwen/qwen-turbo")
    fallback_models_raw = _prompt(
        "OpenRouter fallback models (comma-separated)",
        "",
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
    print("Эти значения будут сохранены в config.local.json.")
    print('Поле ticktick.inbox_project_id по умолчанию остаётся alias "inbox".')
    print(
        "Если TickTick API не сможет автоматически определить real Inbox ID, "
        'позже укажите его вручную, например "inbox121427197".'
    )

    client_id = _prompt("TickTick client_id")
    client_secret = _prompt("TickTick client_secret")
    redirect_uri = _prompt(
        "TickTick redirect_uri",
        "http://localhost:8765/callback",
    )
    scope = _prompt("TickTick scope", "tasks:write tasks:read")

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
    store.save(config)
    print(f"Конфиг сохранен в {store.path}")
    return config

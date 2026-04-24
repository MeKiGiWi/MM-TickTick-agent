# TickTick Chat Agent

Простой CLI-агент для TickTick. Пользователь пишет обычным текстом, модель отвечает по-русски и при необходимости сама выбирает TickTick tools через OpenRouter tool calling.

## Архитектура

- `app/llm/openrouter.py`:
  `OpenRouterClient` отправляет `messages + tools` в OpenRouter, а `OpenRouterToolLoop` исполняет tool calls до финального текстового ответа.
- `app/tools/registry.py`:
  `ToolRegistry` загружает tool descriptions и JSON schemas из `app/tools/specs/ticktick_tools.json`, связывает их с Python handlers и выполняет tools.
- `app/providers/ticktick/client.py`:
  `TickTickApiProvider` реализует реальные вызовы TickTick API.
- `app/providers/mock/ticktick.py`:
  мок-провайдер для локальной разработки и тестов.
- `app/chat/session.py`:
  CLI-сессия, история сообщений и runtime context для относительных дат.

Источник истины для tools один:

- модель получает tools только из `ToolRegistry`
- `ToolRegistry` читает descriptions и schemas из `app/tools/specs/ticktick_tools.json`

## Доступные tools

- `create_task`
- `list_tasks`
- `get_task_details`
- `create_subtasks`
- `update_task`
- `update_task_by_search`
- `list_projects`
- `list_upcoming_tasks`
- `move_task`
- `mark_complete`

## Запуск

### Локально

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m app
```

### Через Docker Compose

```bash
cp .env.example .env
docker compose run --rm app
```

## Конфиг

Основные настройки можно положить в `config.local.json` или в `.env`.

Минимум для OpenRouter:

```json
{
  "openrouter": {
    "api_key": "or-your-openrouter-key",
    "base_url": "https://openrouter.ai/api/v1",
    "model": "openrouter/free",
    "fallback_models": [
      "openai/gpt-4o-mini",
      "anthropic/claude-3.5-sonnet"
    ],
    "reasoning_enabled": true
  },
  "ticktick": {
    "provider": "mock"
  }
}
```

`fallback_models` прокидываются в OpenRouter как `extra_body.models`, поэтому при `429`/rate-limit и других ошибках роутер может автоматически перейти на следующую модель. Поверх этого клиент CLI дополнительно перебирает список локально, если OpenRouter всё же вернул ошибку наружу.

Для реального TickTick provider нужны `client_id`, `client_secret`, `redirect_uri` и `access_token` или OAuth setup через CLI.

## Тесты

```bash
python -m pytest
```

# TickTick Chat Agent

Простой CLI-агент для TickTick с OpenRouter tool calling. Приложение остаётся небольшим: без веб-интерфейса, без БД, с русскими ответами и с мок-провайдером для разработки и тестов.

## Архитектура

- `app/chat/session.py`
  CLI-цикл, история сообщений и `Runtime context` для относительных дат.
- `app/chat/prompts.py`
  Короткий доменный prompt без одноразовых сценариев.
- `app/llm/openrouter.py`
  Клиент OpenRouter с локальным fallback, классификацией ошибок и tool loop с ограничением шагов.
- `app/providers/ticktick/client.py`
  Реальный TickTick provider с явным разрешением проектов, поддержкой `parentId` и composite-операциями.
- `app/providers/mock/ticktick.py`
  Мок-провайдер, совместимый с теми же интерфейсами.
- `app/tools/specs/ticktick_tools.json`
  Единственный источник истины для tool names, описаний и JSON schemas.
- `app/tools/registry.py`
  Тонкий реестр: загружает specs, регистрирует handlers, парсит JSON args, исполняет tools и сериализует результат.
- `app/tools/handlers.py`
  Конкретные tool handlers.
- `app/tools/presenter.py`
  Подготовка ответов tools для LLM и CLI, включая локализованные даты.
- `app/tools/task_search.py`
  Поиск и разрешение неоднозначностей по задачам и проектам.

## Модель TickTick

- Проект содержит задачи.
- Задача принадлежит проекту.
- Подзадача это обычная задача с `parentId`.
- Алиасы `inbox`, `default` и `входящие` трактуются как ссылка на реальный TickTick Inbox.
- При создании задач provider всегда возвращает реальный `project_id`, даже если TickTick ответил неполным payload.

## Inbox и проекты

- Inbox это специальный default project.
- В tools и prompt/specs для Inbox используется только alias `project_id="inbox"`.
- Alias `inbox` не равен реальному TickTick `project_id`. Для API нужен real id вида `inbox121427197`.
- Для создания задачи в Inbox `project_id` можно не передавать.
- Для просмотра Inbox: `list_tasks(project_id="inbox")`.
- Для переноса в Inbox: `move_task(task_id=<real task id>, project_id="inbox")`.
- Обычные проекты можно указывать по real `project_id` или точному имени.
- `/project` может не возвращать Inbox как обычный проект, поэтому provider отдельно резолвит и кэширует real Inbox ID.
- Если real Inbox ID однажды найден, provider переиспользует его даже когда Inbox потом становится пустым.

## Доступные tools

- `create_task`
- `create_task_with_subtasks`
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
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python3 -m app
```

### Через Docker Compose

```bash
docker compose run --rm --service-ports app
```

При первом запуске CLI-wizard создаст `config.local.json` и при выборе `ticktick` запустит OAuth login.

## Конфиг

Настройки приложения и локальные секреты хранятся в `config.local.json`. Файл `.env.example` оставлен только как минимальная заглушка, чтобы не дублировать те же поля в двух местах.

Рекомендуемая конфигурация OpenRouter:

```json
{
  "openrouter": {
    "api_key": "or-your-openrouter-key",
    "base_url": "https://openrouter.ai/api/v1",
    "model": "qwen/qwen-turbo",
    "fallback_models": [
      "openai/gpt-4o-mini"
    ],
    "reasoning_enabled": false,
    "max_tool_steps": 4
  },
  "ticktick": {
    "provider": "mock"
  }
}
```

Рекомендации:

- Используйте один механизм fallback: локальный перебор `fallback_models` в коде. `extra_body.models` не используется.
- Для free-моделей держите хотя бы одну не-free fallback-модель, если хотите переживать `503 no healthy upstream`.
- `reasoning_enabled` по умолчанию выключен: для этого CLI-агента это дешевле и предсказуемее.

Для реального TickTick provider нужны `client_id`, `client_secret`, `redirect_uri` и `access_token`.

Если official TickTick API не смог автоматически вывести Inbox ID, укажите его вручную:

```json
{
  "ticktick": {
    "provider": "ticktick",
    "inbox_project_id": "inbox121427197"
  }
}
```

Подсказки:

- Значение `"inbox"` в `ticktick.inbox_project_id` трактуется только как alias или unknown, а не как real TickTick project id.
- Real Inbox ID часто можно увидеть в результате `list_tasks(project_id="inbox")`, когда в Inbox есть хотя бы одна задача.
- Если у вас доступен TickTick web/API status view, real Inbox ID можно взять и оттуда.

## Качество

- Тесты: `python3 -m pytest`
- Линтер: `python3 -m ruff check .`
- Форматирование: `python3 -m ruff format .`

## Что изменилось

- Репозиторий очищен от кэшей, локальных конфигов и лишних файлов упаковки.
- `ToolRegistry` стал тонким, а доменная логика вынесена в отдельные модули.
- TickTick provider теперь надёжно разрешает реальный Inbox, корректно создаёт подзадачи и поддерживает composite tool.
- OpenRouter-клиент упростил fallback и стал возвращать более понятные ошибки для rate limit, unavailable upstream и network/config проблем.

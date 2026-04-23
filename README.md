Track: A

# TickTick Chat Agent

CLI-приложение без UI, где пользователь общается с агентом обычным текстом, а агент сам решает, отвечать напрямую или вызывать TickTick tools через OpenRouter tool calling.

## Что уже есть

- chat-only интерфейс без slash-команд
- локальный setup flow с `config.local.json`
- TickTick OAuth login flow с сохранением токена в `config.local.json`
- OpenRouter client и прозрачный tool loop в стиле OpenAI/OpenRouter
- tool registry с real function tools
- mock TickTick provider для разработки без аккаунта
- базовый `Clarify Agent` для поиска больших и размытых задач
- интерактивная chat session с историей сообщений в памяти
- тесты на setup, clarify, tools и tool loop

## Структура

```text
app/
  __main__.py
  agents/
    clarify.py
  chat/
    prompts.py
    session.py
  config/
    setup.py
  domain/
    models.py
  llm/
    openrouter.py
  providers/
    mock/
      ticktick.py
    ticktick/
      base.py
      client.py
  services/
    provider_factory.py
  storage/
    config_store.py
  tools/
    base.py
    registry.py
  utils/
    json.py
tests/
README.md
Dockerfile
pyproject.toml
.gitignore
config.local.example.json
```

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m app
```

На первом запуске приложение спросит:

1. `OpenRouter API key`
2. модель OpenRouter
3. тип TickTick provider: `mock` или `ticktick`
4. TickTick OAuth app settings
5. если выбран `ticktick`, запускается OAuth login и `access_token` сохраняется локально

Все это сохраняется локально в `config.local.json`.

## Куда вставлять OpenRouter key

Есть два варианта:

1. Просто запустить `python -m app` и на первом вопросе вставить ключ.
2. Создать в корне проекта файл `config.local.json` по образцу `config.local.example.json` и вставить ключ в поле:

```json
{
  "openrouter": {
    "api_key": "or-your-key-here"
  }
}
```

Для MVP ключ не хранится в env vars.

## Пример `config.local.json`

```json
{
  "openrouter": {
    "api_key": "or-your-openrouter-key",
    "base_url": "https://openrouter.ai/api/v1",
    "model": "meta-llama/llama-3.3-70b-instruct:free"
  },
  "ticktick": {
    "provider": "ticktick",
    "client_id": "your-ticktick-client-id",
    "client_secret": "your-ticktick-client-secret",
    "redirect_uri": "http://localhost:8765/callback",
    "access_token": "ticktick-access-token",
    "scope": "tasks:write tasks:read",
    "auth_state": "last-oauth-state",
    "inbox_project_id": "inbox"
  }
}
```

## TickTick OAuth

Для реального логина нужен TickTick app с `client_id`, `client_secret` и зарегистрированным `redirect_uri`.

Рекомендуемый redirect для MVP:

```text
http://localhost:8765/callback
```

Flow такой:

1. В setup выбираешь `provider=ticktick`
2. Приложение показывает URL авторизации
3. Если redirect на `localhost`, агент ждет callback автоматически
4. Если автоматический callback не сработал, можно вставить в терминал полный redirect URL или просто `code`
5. `access_token` сохраняется в корне проекта в `config.local.json`

## Как это работает

### Tool calling loop

1. В модель отправляются `messages + tools`
2. Модель может вернуть `tool_calls`
3. Локально вызывается Python function
4. Результат добавляется как `role=tool`
5. Выполняется повторный запрос в модель

Все это реализовано в [app/llm/openrouter.py](/Users/daniil/code/mai/Matmod/app/llm/openrouter.py) и [app/tools/registry.py](/Users/daniil/code/mai/Matmod/app/tools/registry.py).

### Доступные tools

- `list_tasks`
- `get_task_details`
- `create_subtasks`
- `update_task`
- `list_projects`
- `move_task`
- `mark_complete`

### Clarify Agent

`Clarify Agent` сейчас использует локальную эвристику:

- ищет большие и размытые формулировки
- классифицирует задачу как `single_action`, `project`, `unclear`
- выставляет `concrete`, `vague`, `needs_breakdown`
- предлагает 3-5 подзадач
- не создает подзадачи без явного согласия пользователя

Реализация: [app/agents/clarify.py](/Users/daniil/code/mai/Matmod/app/agents/clarify.py).

## TickTick provider abstraction

- `MockTickTickProvider` используется по умолчанию
- `TickTickApiProvider` заложен как реальный адаптер под Open API
- дальнейший шаг: добавить полноценный OAuth flow и точное маппирование схем TickTick API

Документация для интеграции лежит в [ticktick_open_api_codex_guide.md](/Users/daniil/code/mai/Matmod/ticktick_open_api_codex_guide.md).

## Запуск тестов

```bash
pytest
```

## Ограничения текущего MVP

- real TickTick OAuth уже есть, но refresh token flow пока не реализован
- real TickTick provider заложен как стартовая абстракция и все еще потребует уточнения полей ответа API
- история чата хранится только в памяти текущего процесса
- Clarify Agent пока эвристический, без отдельной специализированной модели

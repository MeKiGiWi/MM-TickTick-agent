Track: A

# TickTick Chat Agent

CLI-приложение без UI, где пользователь общается с агентом обычным текстом, а агент сам решает, отвечать напрямую или вызывать TickTick tools через OpenRouter tool calling.

## Что уже есть

- chat-only интерфейс без slash-команд
- локальный setup flow с `config.local.json`
- TickTick OAuth login flow с сохранением токена в `config.local.json`
- OpenRouter client и прозрачный tool loop в стиле OpenAI/OpenRouter
- tool registry с real function tools
- создание задач через chat-agent, включая real TickTick provider
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
compose.yaml
pyproject.toml
.gitignore
.env.example
config.local.example.json
```

## Быстрый старт

### Локально через Docker Compose

Это основной способ локального запуска CLI.

1. Создай `.env`:

```bash
cp .env.example .env
```

2. Заполни хотя бы `OPENROUTER_API_KEY`.

3. Запусти интерактивный CLI:

```bash
docker compose run --rm app
```

Compose уже включает:

- интерактивный режим через `stdin_open: true` и `tty: true`
- published port `8765:8765` для TickTick OAuth callback
- bind mount всего репозитория в `/app`, поэтому локальный `config.local.json` сохраняется на хосте и переживает перезапуски

Дополнительный сценарий:

```bash
docker compose up
```

Это запускает тот же CLI через compose без длинной команды `docker run ...`.

### Локально без Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m app
```

На первом запуске CLI теперь спрашивает только короткий минимум:

1. `OpenRouter API key`
2. `OpenRouter model` с дефолтом `openrouter/free`
3. `TickTick provider` (`mock` или `ticktick`)

Если выбран `mock`, setup сразу завершается и сохраняет `config.local.json`.

Если выбран `ticktick`, wizard:

1. коротко напоминает, что нужен TickTick Developer app
2. читает `TICKTICK_CLIENT_ID`, `TICKTICK_CLIENT_SECRET`, `TICKTICK_REDIRECT_URI`, `TICKTICK_SCOPE` из env, если они заданы
3. спрашивает только недостающие поля
4. запускает понятный OAuth flow и сохраняет `access_token` локально

Все это сохраняется локально в `config.local.json`.

## Куда вставлять OpenRouter key

Есть три варианта:

1. Для Docker Compose положить ключ в `.env` как `OPENROUTER_API_KEY`.
2. Просто запустить `python -m app` и на первом вопросе вставить ключ.
3. Создать в корне проекта файл `config.local.json` по образцу `config.local.example.json` и вставить ключ в поле:

```json
{
  "openrouter": {
    "api_key": "or-your-key-here"
  }
}
```

При first-run setup `OPENROUTER_API_KEY` и `OPENROUTER_MODEL` тоже читаются из env, если они заданы.

## Пример `config.local.json`

```json
{
  "openrouter": {
    "api_key": "or-your-openrouter-key",
    "base_url": "https://openrouter.ai/api/v1",
    "model": "openrouter/free",
    "reasoning_enabled": true
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

Этот URI должен совпадать с настройкой в TickTick Developer App.

Flow теперь выглядит так:

1. В setup выбираешь `provider=ticktick`
2. CLI печатает короткое объяснение шагов и `Authorization URL`
3. Если `redirect_uri` указывает на `localhost`, агент пробует принять callback автоматически
4. Если callback не дошел, можно вставить в терминал полный redirect URL или просто `code`
5. `access_token` сохраняется в корне проекта в `config.local.json`

### Docker-friendly OAuth

Если приложение запущено в контейнере, callback server биндуется docker-friendly образом, а не только на `127.0.0.1` внутри контейнера. Это важно для сценария с published port.

Для локального compose-сценария достаточно:

```bash
cp .env.example .env
docker compose run --rm app
```

Если используешь реальный TickTick, задай в `.env`:

```dotenv
TICKTICK_CLIENT_ID=your-client-id
TICKTICK_CLIENT_SECRET=your-client-secret
TICKTICK_REDIRECT_URI=http://localhost:8765/callback
```

Для `mock` можно оставить TickTick-переменные пустыми и просто выбрать `mock` в wizard.

В compose-режиме CLI:

1. не полагается на auto-open браузера как на основной путь
2. печатает URL авторизации в явном виде
3. ждет callback на опубликованном порту
4. оставляет очевидный manual fallback через полный redirect URL или `code`

Если published port или redirect не настроены, manual paste flow остается рабочим.

## Где хранится локальный config

Приложение сохраняет локальный config в корне репозитория:

```text
./config.local.json
```

В `compose.yaml` примонтирован весь проект в `/app`, поэтому `config.local.json` создается и обновляется прямо на хосте. Благодаря этому настройки и сохраненный `access_token` переживают `docker compose run --rm app` и `docker compose up`.

## OpenRouter free + reasoning

По умолчанию используется модель `openrouter/free`.

Запросы идут через OpenAI SDK с:

```python
from openai import OpenAI

client = OpenAI(
    api_key="or-your-key",
    base_url="https://openrouter.ai/api/v1",
)
```

Reasoning включен через `extra_body={"reasoning": {"enabled": True}}`. Если OpenRouter возвращает `reasoning_details`, агент сохраняет их в assistant history и отправляет обратно в следующий запрос без изменений, так что continuation reasoning между ходами не теряется.

## Как это работает

### Tool calling loop

1. В модель отправляются `messages + tools`
2. Модель может вернуть `tool_calls`
3. Локально вызывается Python function
4. Результат добавляется как `role=tool`
5. Выполняется повторный запрос в модель

Все это реализовано в [app/llm/openrouter.py](/Users/daniil/code/mai/Matmod/app/llm/openrouter.py) и [app/tools/registry.py](/Users/daniil/code/mai/Matmod/app/tools/registry.py). Tool loop по-прежнему работает через `tool_calls`, а assistant messages теперь также сохраняют `reasoning_details`, если они пришли от роутера/модели. Если tool возвращает ошибку, в `tool` message уходит структурированный объект с `error`, чтобы модель не подменяла это выдуманным "пусто".

### Доступные tools

- `create_task`
- `list_tasks`
- `get_task_details`
- `create_subtasks`
- `update_task`
- `list_projects`
- `move_task`
- `mark_complete`

`create_task` вызывается по явной просьбе пользователя создать задачу. Если `project_id` не указан, агент пытается использовать `ticktick.inbox_project_id` из локального конфига. Если этот id больше невалиден, provider сначала пробует выбрать доступный default project, а если это невозможно, возвращает понятную tool error.

`list_projects` старается не терять контекст inbox/default project. Если TickTick API не вернул настроенный `inbox_project_id` в общем списке проектов, CLI все равно показывает этот контекст как configured inbox, чтобы сценарий "а inbox?" не выглядел как пропажа проекта.

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

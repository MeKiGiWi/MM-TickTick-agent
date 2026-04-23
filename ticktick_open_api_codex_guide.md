# TickTick Open API — практическая документация для Codex

> Версия документа: 2026-04-23  
> Назначение: дать Codex **строгую, прикладную и безопасную** инструкцию по работе с TickTick Open API без лишних допущений.  
> Основа: официальный TickTick Open API + предоставленный пользователем текст спецификации.  
> Источники для ручной проверки человеком:
>
> - https://developer.ticktick.com/
> - https://help.ticktick.com/articles/7055781495671095296

---

## 1) Что это за API

TickTick Open API — это HTTP JSON API для работы с:

- задачами (`Task`)
- проектами/списками (`Project`)
- фокус-сессиями (`Focus`)
- привычками (`Habit`)
- чек-инами привычек (`Habit Check-In`)

API использует:

- `OAuth2 Authorization Code Flow`
- `Bearer` access token в заголовке `Authorization`
- базовый домен API: `https://api.ticktick.com`

---

## 2) Нормативные правила для Codex

Ниже — **обязательные правила**, чтобы не генерировать неверные запросы.

1. **Всегда используй `Authorization: Bearer <access_token>`** для вызова Open API.
2. **Не придумывай поля**, которых нет в документации.
3. **Не меняй HTTP-метод**:
   - создание и обновление у TickTick часто идут через `POST`
   - фильтрация и список completed tasks тоже идут через `POST`, а не `GET`
4. **Форматы дат важны**:
   - большинство datetime полей: `"yyyy-MM-dd'T'HH:mm:ssZ"`  
     пример: `"2026-04-07T08:00:00+0000"`
   - `habit check-in stamp` и `targetStartDate`: `YYYYMMDD` как integer  
     пример: `20260407`
5. **Учитывай различие статусов**:
   - `Task.status`: `0 = Normal`, `2 = Completed`
   - `ChecklistItem.status`: `0 = Normal`, `1 = Completed`
6. **При обновлении задачи** (`POST /open/v1/task/{taskId}`) передавай в body как минимум:
   - `id`
   - `projectId`
   Даже если `taskId` уже есть в path.
7. **`Move Task` принимает массив операций**, а не объект.
8. **`Focus` range ограничен 30 днями**: если диапазон больше 30 дней, сервер сам сдвигает `from`.
9. **Не рассчитывай на pagination**, если она не описана для конкретного endpoint.
10. **К полям `etag` относись как к непрозрачной серверной метадате**. В данной спецификации не описана обязательная optimistic locking семантика.
11. **Будь устойчив к неоднозначным кодам ответа**: в документации местами одновременно указаны `200 OK` и `201 Created`. Реальный код лучше обрабатывать через `response.ok`, а тело — проверять отдельно.
12. **Проверяй регистр enum-значений**:
    - для `Project.kind` используй предпочтительно `"TASK"` или `"NOTE"`
    - для `Task.kind` ориентируйся на `"TEXT"`, `"NOTE"`, `"CHECKLIST"`

---

## 3) Базовые настройки HTTP

### Base URL

```text
https://api.ticktick.com
```

### Общие заголовки

```http
Authorization: Bearer <access_token>
Content-Type: application/json
Accept: application/json
```

> Для получения токена `Content-Type` другой: `application/x-www-form-urlencoded`.

---

## 4) Авторизация OAuth2

TickTick использует **OAuth2 Authorization Code Flow**.

### 4.1. Шаг 1 — отправить пользователя на страницу авторизации

**Authorization URL**

```text
https://ticktick.com/oauth/authorize
```

**Query parameters**

| Параметр | Обязателен | Описание |
|---|---:|---|
| `client_id` | да | ID приложения |
| `scope` | да | space-separated scopes |
| `state` | да | произвольная строка, возвращается обратно |
| `redirect_uri` | да | один из зарегистрированных redirect URI |
| `response_type` | да | фиксированно: `code` |

**Доступные scopes**

```text
tasks:write tasks:read
```

**Пример**

```text
https://ticktick.com/oauth/authorize?scope=tasks:write%20tasks:read&client_id=YOUR_CLIENT_ID&state=RANDOM_STATE&redirect_uri=https%3A%2F%2Fexample.com%2Fcallback&response_type=code
```

### 4.2. Шаг 2 — принять redirect с code

После согласия пользователя TickTick редиректит на `redirect_uri` и добавляет query-параметры:

- `code` — authorization code
- `state` — то же значение, что было передано ранее

### 4.3. Шаг 3 — обменять code на access token

**Token URL**

```text
https://ticktick.com/oauth/token
```

**Метод**

```http
POST
```

**Content-Type**

```http
application/x-www-form-urlencoded
```

**Важно:**  
В документации указано, что `client_id` и `client_secret` передаются через **Basic Auth в заголовке**.

То есть:

```http
Authorization: Basic base64(client_id:client_secret)
```

**Form fields**

| Поле | Обязателен | Описание |
|---|---:|---|
| `code` | да | code из шага 2 |
| `grant_type` | да | `authorization_code` |
| `scope` | да | `tasks:write tasks:read` |
| `redirect_uri` | да | тот же redirect URI |

**Пример curl**

```bash
curl -X POST 'https://ticktick.com/oauth/token' \
  -H 'Authorization: Basic BASE64_CLIENT_ID_COLON_CLIENT_SECRET' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'code=AUTH_CODE' \
  --data-urlencode 'grant_type=authorization_code' \
  --data-urlencode 'scope=tasks:write tasks:read' \
  --data-urlencode 'redirect_uri=https://example.com/callback'
```

**Ожидаемый ответ (фрагмент)**

```json
{
  "access_token": "access token value"
}
```

---

## 5) Форматы и перечисления

### 5.1. Формат datetime

Во многих endpoint’ах используется:

```text
yyyy-MM-dd'T'HH:mm:ssZ
```

Пример:

```text
2019-11-13T03:00:00+0000
2026-04-07T09:25:00+0800
```

### 5.2. Формат даты-штампа для habits

```text
YYYYMMDD
```

Пример:

```text
20260407
```

### 5.3. Priority у задач

| Значение | Смысл |
|---:|---|
| `0` | None |
| `1` | Low |
| `3` | Medium |
| `5` | High |

### 5.4. Status у задач и subtasks

**Task.status**

| Значение | Смысл |
|---:|---|
| `0` | Normal |
| `2` | Completed |

**ChecklistItem.status**

| Значение | Смысл |
|---:|---|
| `0` | Normal |
| `1` | Completed |

### 5.5. Focus type

| Значение | Смысл |
|---:|---|
| `0` | Pomodoro |
| `1` | Timing |

### 5.6. Project kind

| Значение |
|---|
| `"TASK"` |
| `"NOTE"` |

### 5.7. Task kind

| Значение |
|---|
| `"TEXT"` |
| `"NOTE"` |
| `"CHECKLIST"` |

---

## 6) Быстрый рабочий сценарий

Обычный поток интеграции:

1. Получить OAuth2 access token
2. Получить проекты: `GET /open/v1/project`
3. Выбрать `projectId`
4. Создать задачу: `POST /open/v1/task`
5. При необходимости:
   - обновить задачу
   - завершить задачу
   - удалить задачу
   - перенести задачу между проектами
   - фильтровать задачи
6. Для аналитики/трекеров:
   - focus endpoints
   - habit endpoints

---

# 7) API Reference

---

## 7.1. Task

### 7.1.1. Get Task By Project ID And Task ID

```http
GET /open/v1/project/{projectId}/task/{taskId}
```

**Path parameters**

| Имя | Тип | Обязателен | Описание |
|---|---|---:|---|
| `projectId` | string | да | ID проекта |
| `taskId` | string | да | ID задачи |

**Пример**

```bash
curl -X GET 'https://api.ticktick.com/open/v1/project/PROJECT_ID/task/TASK_ID' \
  -H 'Authorization: Bearer ACCESS_TOKEN'
```

**Возвращает**: объект `Task`

---

### 7.1.2. Create Task

```http
POST /open/v1/task
```

**Body**

| Поле | Тип | Обязателен | Описание |
|---|---|---:|---|
| `title` | string | да | Заголовок задачи |
| `projectId` | string | да | ID проекта |
| `content` | string | нет | Контент задачи |
| `desc` | string | нет | Описание checklist |
| `isAllDay` | boolean | нет | На весь день |
| `startDate` | date-time string | нет | Старт |
| `dueDate` | date-time string | нет | Дедлайн |
| `timeZone` | string | нет | Таймзона |
| `reminders` | string[] | нет | Триггеры напоминаний |
| `repeatFlag` | string | нет | RRULE |
| `priority` | integer | нет | 0/1/3/5 |
| `sortOrder` | integer | нет | Порядок сортировки |
| `items` | array | нет | Подзадачи |

**Структура `items[]`**

| Поле | Тип | Обязателен | Описание |
|---|---|---:|---|
| `title` | string | нет | Заголовок подзадачи |
| `startDate` | date-time string | нет | Старт |
| `isAllDay` | boolean | нет | На весь день |
| `sortOrder` | integer | нет | Порядок |
| `timeZone` | string | нет | Таймзона |
| `status` | integer | нет | 0/1 |
| `completedTime` | date-time string | нет | Время завершения |

**Минимальный body**

```json
{
  "title": "Task Title",
  "projectId": "6226ff9877acee87727f6bca"
}
```

**Практический пример**

```json
{
  "title": "Write release notes",
  "projectId": "6226ff9877acee87727f6bca",
  "content": "Draft notes for v1.3",
  "isAllDay": false,
  "startDate": "2026-04-23T09:00:00+0000",
  "dueDate": "2026-04-23T17:00:00+0000",
  "timeZone": "UTC",
  "priority": 3,
  "items": [
    {
      "title": "Collect merged PRs",
      "status": 0
    },
    {
      "title": "Draft highlights",
      "status": 0
    }
  ]
}
```

**Пример curl**

```bash
curl -X POST 'https://api.ticktick.com/open/v1/task' \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Write release notes",
    "projectId": "6226ff9877acee87727f6bca"
  }'
```

**Возвращает**: объект `Task`

---

### 7.1.3. Update Task

```http
POST /open/v1/task/{taskId}
```

**ВАЖНО:**  
Несмотря на наличие `taskId` в path, документация требует в body:

- `id`
- `projectId`

**Path parameters**

| Имя | Тип | Обязателен |
|---|---|---:|
| `taskId` | string | да |

**Body**

| Поле | Тип | Обязателен | Описание |
|---|---|---:|---|
| `id` | string | да | ID задачи |
| `projectId` | string | да | ID проекта |
| `title` | string | нет | Заголовок |
| `content` | string | нет | Контент |
| `desc` | string | нет | Описание checklist |
| `isAllDay` | boolean | нет | На весь день |
| `startDate` | date-time string | нет | Старт |
| `dueDate` | date-time string | нет | Дедлайн |
| `timeZone` | string | нет | Таймзона |
| `reminders` | string[] | нет | Напоминания |
| `repeatFlag` | string | нет | RRULE |
| `priority` | integer | нет | 0/1/3/5 |
| `sortOrder` | integer | нет | Порядок |
| `items` | array | нет | Подзадачи |

**Минимальный безопасный body**

```json
{
  "id": "TASK_ID",
  "projectId": "PROJECT_ID"
}
```

**Типичный body**

```json
{
  "id": "63b7bebb91c0a5474805fcd4",
  "projectId": "6226ff9877acee87727f6bca",
  "title": "Task Title",
  "priority": 1
}
```

**Пример curl**

```bash
curl -X POST 'https://api.ticktick.com/open/v1/task/TASK_ID' \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "TASK_ID",
    "projectId": "PROJECT_ID",
    "title": "Updated title",
    "priority": 5
  }'
```

**Возвращает**: объект `Task`

---

### 7.1.4. Complete Task

```http
POST /open/v1/project/{projectId}/task/{taskId}/complete
```

**Path parameters**

| Имя | Тип | Обязателен |
|---|---|---:|
| `projectId` | string | да |
| `taskId` | string | да |

**Пример**

```bash
curl -X POST 'https://api.ticktick.com/open/v1/project/PROJECT_ID/task/TASK_ID/complete' \
  -H 'Authorization: Bearer ACCESS_TOKEN'
```

**Возвращает**: обычно пустой ответ (`No Content`)

---

### 7.1.5. Delete Task

```http
DELETE /open/v1/project/{projectId}/task/{taskId}
```

**Path parameters**

| Имя | Тип | Обязателен |
|---|---|---:|
| `projectId` | string | да |
| `taskId` | string | да |

**Пример**

```bash
curl -X DELETE 'https://api.ticktick.com/open/v1/project/PROJECT_ID/task/TASK_ID' \
  -H 'Authorization: Bearer ACCESS_TOKEN'
```

---

### 7.1.6. Move Task

```http
POST /open/v1/task/move
```

Переносит одну или несколько задач между проектами.

**ВАЖНО:** body — это **JSON-массив**, даже если переносится одна задача.

**Body element**

| Поле | Тип | Обязателен | Описание |
|---|---|---:|---|
| `fromProjectId` | string | да | Исходный проект |
| `toProjectId` | string | да | Целевой проект |
| `taskId` | string | да | ID задачи |

**Пример body**

```json
[
  {
    "fromProjectId": "69a850ef1c20d2030e148fdd",
    "toProjectId": "69a850f41c20d2030e148fdf",
    "taskId": "69a850f8b9061f374d54a046"
  }
]
```

**Пример ответа**

```json
[
  {
    "id": "69a850f8b9061f374d54a046",
    "etag": "43p2zso1"
  }
]
```

---

### 7.1.7. List Completed Tasks

```http
POST /open/v1/task/completed
```

Возвращает completed tasks по проектам и/или временному диапазону.

**Body**

| Поле | Тип | Обязателен | Описание |
|---|---|---:|---|
| `projectIds` | string[] | нет | Список project IDs |
| `startDate` | date-time string | нет | `completedTime >= startDate` |
| `endDate` | date-time string | нет | `completedTime <= endDate` |

**Пример body**

```json
{
  "projectIds": [
    "69a850f41c20d2030e148fdf"
  ],
  "startDate": "2026-03-01T00:58:20.000+0000",
  "endDate": "2026-03-05T10:58:20.000+0000"
}
```

**Возвращает**: `Task[]`

---

### 7.1.8. Filter Tasks

```http
POST /open/v1/task/filter
```

Продвинутая фильтрация задач.

**Body**

| Поле | Тип | Обязателен | Описание |
|---|---|---:|---|
| `projectIds` | string[] | нет | Фильтр по проектам |
| `startDate` | date-time string | нет | `task.startDate >= startDate` |
| `endDate` | date-time string | нет | `task.startDate <= endDate` |
| `priority` | integer[] | нет | Приоритеты: 0/1/3/5 |
| `tag` | string[] | нет | Задача должна содержать все теги |
| `status` | integer[] | нет | Например `[0]` или `[2]` |

**Важно:**  
В табличной части исходной документации встречается опечатка `proiority`, но в примере запроса используется `priority`. Для интеграции используй **`priority`**.

**Пример body**

```json
{
  "projectIds": [
    "69a850f41c20d2030e148fdf"
  ],
  "startDate": "2026-03-01T00:58:20.000+0000",
  "endDate": "2026-03-06T10:58:20.000+0000",
  "priority": [0],
  "tag": ["urgent"],
  "status": [0]
}
```

**Возвращает**: `Task[]`

---

## 7.2. Project

### 7.2.1. Get User Project

```http
GET /open/v1/project
```

Возвращает список проектов пользователя.

**Пример**

```bash
curl -X GET 'https://api.ticktick.com/open/v1/project' \
  -H 'Authorization: Bearer ACCESS_TOKEN'
```

**Возвращает**: `Project[]`

---

### 7.2.2. Get Project By ID

```http
GET /open/v1/project/{projectId}
```

**Path parameters**

| Имя | Тип | Обязателен |
|---|---|---:|
| `projectId` | string | да |

**Возвращает**: `Project`

---

### 7.2.3. Get Project With Data

```http
GET /open/v1/project/{projectId}/data
```

Возвращает:

- `project`
- `tasks`
- `columns`

**Важно:**  
По определению `ProjectData.tasks` — это **undone tasks under project**, то есть незавершённые задачи проекта.

**Возвращает**: `ProjectData`

---

### 7.2.4. Create Project

```http
POST /open/v1/project
```

**Body**

| Поле | Тип | Обязателен | Описание |
|---|---|---:|---|
| `name` | string | да | Имя проекта |
| `color` | string | нет | Например `#F18181` |
| `sortOrder` | integer | нет | Порядок сортировки |
| `viewMode` | string | нет | `"list"`, `"kanban"`, `"timeline"` |
| `kind` | string | нет | `"TASK"` или `"NOTE"` |

**Рекомендация:**  
Передавай `kind` в верхнем регистре (`"TASK"` / `"NOTE"`), даже если в одном из примеров встречается `"task"`.

**Пример body**

```json
{
  "name": "project name",
  "color": "#F18181",
  "viewMode": "list",
  "kind": "TASK"
}
```

---

### 7.2.5. Update Project

```http
POST /open/v1/project/{projectId}
```

**Path parameters**

| Имя | Тип | Обязателен |
|---|---|---:|
| `projectId` | string | да |

**Body**

| Поле | Тип | Обязателен |
|---|---|---:|
| `name` | string | нет |
| `color` | string | нет |
| `sortOrder` | integer | нет |
| `viewMode` | string | нет |
| `kind` | string | нет |

**Пример body**

```json
{
  "name": "Project Name",
  "color": "#F18181",
  "viewMode": "list",
  "kind": "TASK"
}
```

---

### 7.2.6. Delete Project

```http
DELETE /open/v1/project/{projectId}
```

**Path parameters**

| Имя | Тип | Обязателен |
|---|---|---:|
| `projectId` | string | да |

---

## 7.3. Focus

### 7.3.1. Get Focus By Focus ID

```http
GET /open/v1/focus/{focusId}?type={type}
```

**Path parameters**

| Имя | Тип | Обязателен |
|---|---|---:|
| `focusId` | string | да |

**Query parameters**

| Имя | Тип | Обязателен | Описание |
|---|---|---:|---|
| `type` | integer | да | `0 = Pomodoro`, `1 = Timing` |

**Пример**

```bash
curl -X GET 'https://api.ticktick.com/open/v1/focus/FOCUS_ID?type=0' \
  -H 'Authorization: Bearer ACCESS_TOKEN'
```

**Возвращает**: `OpenFocus`

---

### 7.3.2. Get Focuses By Time Range

```http
GET /open/v1/focus?from={from}&to={to}&type={type}
```

**Query parameters**

| Имя | Тип | Обязателен | Описание |
|---|---|---:|---|
| `from` | string | да | Начало диапазона |
| `to` | string | да | Конец диапазона |
| `type` | integer | да | `0` или `1` |

**Важно:**  
Если диапазон превышает 30 дней, сервер автоматически сдвигает `from` на 30 дней до `to`.

**Пример**

```bash
curl -X GET 'https://api.ticktick.com/open/v1/focus?from=2026-04-01T00:00:00+0800&to=2026-04-02T00:00:00+0800&type=1' \
  -H 'Authorization: Bearer ACCESS_TOKEN'
```

**Возвращает**: `OpenFocus[]`

---

### 7.3.3. Delete Focus

```http
DELETE /open/v1/focus/{focusId}?type={type}
```

**Path parameters**

| Имя | Тип | Обязателен |
|---|---|---:|
| `focusId` | string | да |

**Query parameters**

| Имя | Тип | Обязателен |
|---|---|---:|
| `type` | integer | да |

**Возвращает**: урезанный `OpenFocus` (например только `id` и `type`)

---

## 7.4. Habit

### 7.4.1. Get Habit By Habit ID

```http
GET /open/v1/habit/{habitId}
```

**Path parameters**

| Имя | Тип | Обязателен |
|---|---|---:|
| `habitId` | string | да |

**Возвращает**: `OpenHabit`

---

### 7.4.2. Get All Habits

```http
GET /open/v1/habit
```

**Параметров нет**

**Возвращает**: `OpenHabit[]`

---

### 7.4.3. Create Habit

```http
POST /open/v1/habit
```

**Body**

| Поле | Тип | Обязателен | Описание |
|---|---|---:|---|
| `name` | string | да | До 1000 символов |
| `iconRes` | string | нет | Иконка |
| `color` | string | нет | Цвет |
| `sortOrder` | integer | нет | Сортировка |
| `status` | integer | нет | Статус |
| `encouragement` | string | нет | Текст мотивации |
| `type` | string | нет | Тип привычки |
| `goal` | number | нет | Цель |
| `step` | number | нет | Шаг |
| `unit` | string | нет | Единица |
| `repeatRule` | string | нет | RRULE |
| `reminders` | string[] | нет | Напоминания |
| `recordEnable` | boolean | нет | Включён record |
| `sectionId` | string | нет | Секция |
| `targetDays` | integer | нет | Целевые дни |
| `targetStartDate` | integer | нет | `YYYYMMDD` |
| `completedCycles` | integer | нет | Циклы |
| `exDates` | string[] | нет | Исключённые даты |
| `style` | integer | нет | Стиль |

**Пример body**

```json
{
  "name": "Read",
  "iconRes": "habit_reading",
  "color": "#4D8CF5",
  "type": "Boolean",
  "goal": 1.0,
  "step": 1.0,
  "unit": "Count",
  "repeatRule": "RRULE:FREQ=DAILY;INTERVAL=1",
  "recordEnable": false
}
```

**Возвращает**: `OpenHabit`

---

### 7.4.4. Update Habit

```http
POST /open/v1/habit/{habitId}
```

**Path parameters**

| Имя | Тип | Обязателен |
|---|---|---:|
| `habitId` | string | да |

**Body**: те же поля, что и у Create Habit, но необязательные.

**Важно:**  
Документация отдельно говорит: если `name` пустой, он трактуется как `null`.

**Пример body**

```json
{
  "name": "Read more",
  "goal": 2.0,
  "repeatRule": "RRULE:FREQ=DAILY;INTERVAL=1"
}
```

**Возвращает**: `OpenHabit`

---

### 7.4.5. Create Or Update Habit Check-In

```http
POST /open/v1/habit/{habitId}/checkin
```

**Path parameters**

| Имя | Тип | Обязателен |
|---|---|---:|
| `habitId` | string | да |

**Body**

| Поле | Тип | Обязателен | Описание |
|---|---|---:|---|
| `stamp` | integer | да | `YYYYMMDD` |
| `time` | date-time string | нет | Время check-in |
| `opTime` | date-time string | нет | Время операции |
| `value` | number | нет | По умолчанию `1.0` |
| `goal` | number | нет | По умолчанию `1.0` |
| `status` | integer | нет | Статус |

**Пример body**

```json
{
  "stamp": 20260407,
  "value": 1.0,
  "goal": 1.0
}
```

**Возвращает**: `OpenHabitCheckin`

---

### 7.4.6. Get Habit Check-Ins

```http
GET /open/v1/habit/checkins?habitIds={ids}&from={from}&to={to}
```

**Query parameters**

| Имя | Тип | Обязателен | Описание |
|---|---|---:|---|
| `habitIds` | string | да | ID через запятую |
| `from` | integer | да | `YYYYMMDD` |
| `to` | integer | да | `YYYYMMDD` |

**Пример**

```bash
curl -X GET 'https://api.ticktick.com/open/v1/habit/checkins?habitIds=habit-1,habit-2&from=20260401&to=20260407' \
  -H 'Authorization: Bearer ACCESS_TOKEN'
```

**Возвращает**: `OpenHabitCheckin[]`

---

# 8) Definitions / Data Models

---

## 8.1. ChecklistItem

```ts
type ChecklistItem = {
  id?: string
  title?: string
  status?: 0 | 1
  completedTime?: string // yyyy-MM-dd'T'HH:mm:ssZ
  isAllDay?: boolean
  sortOrder?: number
  startDate?: string // yyyy-MM-dd'T'HH:mm:ssZ
  timeZone?: string
}
```

---

## 8.2. Task

```ts
type Task = {
  id?: string
  projectId?: string
  title?: string
  isAllDay?: boolean
  completedTime?: string
  content?: string
  desc?: string
  dueDate?: string
  items?: ChecklistItem[]
  priority?: 0 | 1 | 3 | 5
  reminders?: string[]
  repeatFlag?: string
  sortOrder?: number
  startDate?: string
  status?: 0 | 2
  timeZone?: string
  kind?: "TEXT" | "NOTE" | "CHECKLIST"
  tags?: string[]
  etag?: string
}
```

> `tags` и `etag` видны в примерах ответов, хотя не все они перечислены в базовом блоке определения `Task`.

---

## 8.3. Project

```ts
type Project = {
  id?: string
  name?: string
  color?: string
  sortOrder?: number
  closed?: boolean
  groupId?: string
  viewMode?: "list" | "kanban" | "timeline"
  permission?: "read" | "write" | "comment"
  kind?: "TASK" | "NOTE"
}
```

---

## 8.4. Column

```ts
type Column = {
  id?: string
  projectId?: string
  name?: string
  sortOrder?: number
}
```

---

## 8.5. ProjectData

```ts
type ProjectData = {
  project?: Project
  tasks?: Task[]      // undone tasks
  columns?: Column[]
}
```

---

## 8.6. OpenPomodoroTaskBrief

```ts
type OpenPomodoroTaskBrief = {
  taskId?: string
  title?: string
  habitId?: string
  timerId?: string
  timerName?: string
  startTime?: string
  endTime?: string
}
```

---

## 8.7. OpenFocus

```ts
type OpenFocus = {
  id?: string
  userId?: number
  type?: 0 | 1
  taskId?: string
  note?: string
  tasks?: OpenPomodoroTaskBrief[]
  status?: number
  startTime?: string
  endTime?: string
  pauseDuration?: number
  adjustTime?: number
  added?: boolean
  createdTime?: string
  modifiedTime?: string
  etimestamp?: number
  etag?: string
  duration?: number
  relationType?: number[]
}
```

---

## 8.8. OpenHabit

```ts
type OpenHabit = {
  id?: string
  name?: string
  iconRes?: string
  color?: string
  sortOrder?: number
  status?: number
  encouragement?: string
  totalCheckIns?: number
  createdTime?: string
  modifiedTime?: string
  archivedTime?: string
  type?: string
  goal?: number
  step?: number
  unit?: string
  etag?: string
  repeatRule?: string
  reminders?: string[]
  recordEnable?: boolean
  sectionId?: string
  targetDays?: number
  targetStartDate?: number // YYYYMMDD
  completedCycles?: number
  exDates?: string[]
  style?: number
}
```

---

## 8.9. OpenHabitCheckinData

```ts
type OpenHabitCheckinData = {
  id?: string
  stamp?: number      // YYYYMMDD
  time?: string
  opTime?: string
  value?: number
  goal?: number
  status?: number
}
```

---

## 8.10. OpenHabitCheckin

```ts
type OpenHabitCheckin = {
  id?: string
  habitId?: string
  createdTime?: string
  modifiedTime?: string
  etag?: string
  year?: number
  checkins?: OpenHabitCheckinData[]
}
```

---

# 9) Copy-paste ready examples

## 9.1. Получить проекты

```bash
curl -X GET 'https://api.ticktick.com/open/v1/project' \
  -H 'Authorization: Bearer ACCESS_TOKEN'
```

## 9.2. Создать проект

```bash
curl -X POST 'https://api.ticktick.com/open/v1/project' \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Backend",
    "color": "#4D8CF5",
    "viewMode": "list",
    "kind": "TASK"
  }'
```

## 9.3. Создать задачу

```bash
curl -X POST 'https://api.ticktick.com/open/v1/task' \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Prepare API client",
    "projectId": "PROJECT_ID",
    "priority": 3
  }'
```

## 9.4. Обновить задачу

```bash
curl -X POST 'https://api.ticktick.com/open/v1/task/TASK_ID' \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "id": "TASK_ID",
    "projectId": "PROJECT_ID",
    "title": "Prepare API client v2",
    "priority": 5
  }'
```

## 9.5. Завершить задачу

```bash
curl -X POST 'https://api.ticktick.com/open/v1/project/PROJECT_ID/task/TASK_ID/complete' \
  -H 'Authorization: Bearer ACCESS_TOKEN'
```

## 9.6. Фильтровать задачи

```bash
curl -X POST 'https://api.ticktick.com/open/v1/task/filter' \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "projectIds": ["PROJECT_ID"],
    "priority": [5],
    "tag": ["urgent"],
    "status": [0]
  }'
```

## 9.7. Создать привычку

```bash
curl -X POST 'https://api.ticktick.com/open/v1/habit' \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Read",
    "type": "Boolean",
    "goal": 1.0,
    "step": 1.0,
    "unit": "Count",
    "repeatRule": "RRULE:FREQ=DAILY;INTERVAL=1",
    "recordEnable": false
  }'
```

## 9.8. Чек-ин привычки

```bash
curl -X POST 'https://api.ticktick.com/open/v1/habit/HABIT_ID/checkin' \
  -H 'Authorization: Bearer ACCESS_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{
    "stamp": 20260407,
    "value": 1.0,
    "goal": 1.0
  }'
```

---

# 10) Ошибки и защита от неверных предположений

## 10.1. Что точно не надо делать

- Не отправлять `GET /open/v1/task/filter`
- Не отправлять объект вместо массива в `POST /open/v1/task/move`
- Не опускать `id` и `projectId` в `Update Task`
- Не путать `Task.status = 2` с `ChecklistItem.status = 1`
- Не передавать `stamp` как ISO-дату
- Не использовать `priority = 2` или `priority = 4` — таких значений нет
- Не полагаться, что все успешные ответы обязательно содержат JSON-тело

## 10.2. Осторожность из-за шероховатостей документации

В исходной спецификации есть мелкие несогласованности:

1. `Filter Tasks`:
   - в таблице есть опечатка `proiority`
   - в примере используется `priority`
   - для интеграции используй `priority`

2. `Create Project`:
   - в одном примере встречается `"kind": "task"`
   - в моделях перечислены `"TASK"` / `"NOTE"`
   - безопаснее использовать uppercase

3. Коды ответа:
   - иногда указаны и `200`, и `201`
   - обрабатывай оба как успешные, но проверяй наличие/отсутствие тела

4. Некоторые поля встречаются в примерах, но не в основном определении модели:
   - например `etag`, `tags`
   - такие поля можно читать, но не стоит считать их обязательными для записи

---

# 11) Рекомендации для генерации клиента

Если Codex будет писать SDK/клиент, ему лучше следовать таким правилам:

## 11.1. Типы

- все ID — `string`
- datetime — `string`
- date stamp (`YYYYMMDD`) — `number`
- priority — union `0 | 1 | 3 | 5`
- task status — union `0 | 2`
- checklist status — union `0 | 1`
- focus type — union `0 | 1`

## 11.2. HTTP-слой

- считать успешными ответы `200..299`
- если `response.status === 204` или тело пустое — не пытаться парсить JSON
- для всех JSON POST-запросов отправлять `Content-Type: application/json`
- для token endpoint использовать `application/x-www-form-urlencoded`

## 11.3. Валидация

Перед отправкой запроса полезно валидировать:

- что `projectId`/`taskId`/`habitId` не пустые
- что datetime соответствует ожидаемому формату
- что `stamp` — восьмизначное число `YYYYMMDD`
- что `priority` входит в `[0, 1, 3, 5]`
- что `type` для focus — `0` или `1`

---

# 12) Минимальный TypeScript-клиент (скелет)

```ts
type TickTickConfig = {
  accessToken: string
  baseUrl?: string
}

class TickTickClient {
  private baseUrl: string
  private accessToken: string

  constructor(config: TickTickConfig) {
    this.baseUrl = config.baseUrl ?? "https://api.ticktick.com"
    this.accessToken = config.accessToken
  }

  private async request<T>(
    path: string,
    init: RequestInit = {}
  ): Promise<T | undefined> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${this.accessToken}`,
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(init.headers ?? {})
      }
    })

    if (!res.ok) {
      const text = await res.text().catch(() => "")
      throw new Error(`TickTick API error ${res.status}: ${text}`)
    }

    const text = await res.text()
    if (!text) return undefined
    return JSON.parse(text) as T
  }

  getProjects() {
    return this.request<Project[]>("/open/v1/project", { method: "GET" })
  }

  getProject(projectId: string) {
    return this.request<Project>(`/open/v1/project/${projectId}`, {
      method: "GET"
    })
  }

  createTask(body: {
    title: string
    projectId: string
    content?: string
    desc?: string
    isAllDay?: boolean
    startDate?: string
    dueDate?: string
    timeZone?: string
    reminders?: string[]
    repeatFlag?: string
    priority?: 0 | 1 | 3 | 5
    sortOrder?: number
    items?: ChecklistItem[]
  }) {
    return this.request<Task>("/open/v1/task", {
      method: "POST",
      body: JSON.stringify(body)
    })
  }

  updateTask(taskId: string, body: {
    id: string
    projectId: string
    title?: string
    content?: string
    desc?: string
    isAllDay?: boolean
    startDate?: string
    dueDate?: string
    timeZone?: string
    reminders?: string[]
    repeatFlag?: string
    priority?: 0 | 1 | 3 | 5
    sortOrder?: number
    items?: ChecklistItem[]
  }) {
    return this.request<Task>(`/open/v1/task/${taskId}`, {
      method: "POST",
      body: JSON.stringify(body)
    })
  }

  completeTask(projectId: string, taskId: string) {
    return this.request<void>(
      `/open/v1/project/${projectId}/task/${taskId}/complete`,
      { method: "POST" }
    )
  }

  deleteTask(projectId: string, taskId: string) {
    return this.request<void>(
      `/open/v1/project/${projectId}/task/${taskId}`,
      { method: "DELETE" }
    )
  }
}
```

---

# 13) Краткая памятка для Codex

```text
Base URL: https://api.ticktick.com
Auth: Bearer access token
OAuth authorize: https://ticktick.com/oauth/authorize
OAuth token: https://ticktick.com/oauth/token

Create task: POST /open/v1/task
Update task: POST /open/v1/task/{taskId} with body.id + body.projectId
Complete task: POST /open/v1/project/{projectId}/task/{taskId}/complete
Delete task: DELETE /open/v1/project/{projectId}/task/{taskId}
Move task: POST /open/v1/task/move with JSON array
Completed tasks: POST /open/v1/task/completed
Filter tasks: POST /open/v1/task/filter
Projects: GET/POST/DELETE /open/v1/project...
Focus type: 0=Pomodoro, 1=Timing
Task priority: 0,1,3,5
Task status: 0=open, 2=completed
Checklist status: 0=open, 1=completed
Habit check-in stamp: YYYYMMDD integer
```

---

# 14) Support

Если нужна ручная проверка или подтверждение спорных моментов, у TickTick в документации указан контакт:

```text
support@ticktick.com
```

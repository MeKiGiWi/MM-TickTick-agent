import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.providers.mock.ticktick import MockTickTickProvider
from app.tools.registry import ToolRegistry


def test_create_task_tool_is_registered() -> None:
    registry = ToolRegistry(MockTickTickProvider(), user_timezone="Europe/Moscow")
    tools = registry.list_openrouter_tools()
    assert any(tool["function"]["name"] == "create_task" for tool in tools)


def test_create_task_tool_uses_mock_provider_defaults() -> None:
    registry = ToolRegistry(MockTickTickProvider(), user_timezone="Europe/Moscow")
    result = registry.execute_tool(
        "create_task",
        json.dumps({"title": "hello world"}, ensure_ascii=False),
    )
    payload = json.loads(result)
    assert payload["title"] == "hello world"
    assert payload["project_id"] == "inbox"
    assert payload["project_name"] == "Inbox"


def test_create_subtasks_tool() -> None:
    registry = ToolRegistry(MockTickTickProvider(), user_timezone="Europe/Moscow")
    result = registry.execute_tool(
        "create_subtasks",
        json.dumps({"task_id": "task-1", "titles": ["Шаг 1", "Шаг 2"]}, ensure_ascii=False),
    )
    payload = json.loads(result)
    assert len(payload) == 2
    assert payload[0]["title"] == "Шаг 1"
    assert payload[0]["project_name"] == "Inbox"


def test_ticktick_all_day_due_date_uses_task_timezone_for_display() -> None:
    registry = ToolRegistry(MockTickTickProvider(), user_timezone="UTC")
    payload = registry._augment_task_payload(
        {
            "id": "task-1",
            "title": "deadline task",
            "due_date": "2026-05-03T21:00:00+0000",
            "time_zone": "Europe/Moscow",
            "is_all_day": True,
        }
    )
    assert payload["due_date_display_date"] == "2026-05-04"
    assert payload["due_date_display_time"] is None
    assert payload["due_date_local_date"] == "2026-05-04"


def test_ticktick_timed_due_date_uses_task_timezone_for_display() -> None:
    registry = ToolRegistry(MockTickTickProvider(), user_timezone="UTC")
    payload = registry._augment_task_payload(
        {
            "id": "task-2",
            "title": "timed task",
            "due_date": "2026-04-24T10:30:00+0000",
            "time_zone": "Europe/Moscow",
            "is_all_day": False,
        }
    )
    assert payload["due_date_display_date"] == "2026-04-24"
    assert payload["due_date_display_time"] == "13:30"
    assert payload["due_date_local_time"] == "13:30"


def test_ticktick_datetime_parser_accepts_milliseconds() -> None:
    parsed = ToolRegistry._parse_ticktick_datetime("2026-05-03T21:00:00.000+0000")
    assert parsed is not None
    assert parsed.isoformat() == "2026-05-03T21:00:00+00:00"


def test_display_fields_keep_backward_compatible_due_date_local_fields() -> None:
    registry = ToolRegistry(MockTickTickProvider(), user_timezone="Europe/Moscow")
    result = registry.execute_tool(
        "create_task",
        json.dumps(
            {
                "title": "deadline task",
                "due_date": "2026-05-03T21:00:00+0000",
            },
            ensure_ascii=False,
        ),
    )
    payload = json.loads(result)
    assert payload["due_date_display_date"] == "2026-05-04"
    assert payload["due_date_local_date"] == payload["due_date_display_date"]


def test_list_projects_tool_returns_all_projects_without_arguments() -> None:
    registry = ToolRegistry(MockTickTickProvider(), user_timezone="Europe/Moscow")
    payload = json.loads(registry.execute_tool("list_projects", "{}"))
    assert [item["name"] for item in payload] == ["Inbox", "Work", "Personal"]


def test_list_projects_tool_filters_by_query() -> None:
    registry = ToolRegistry(MockTickTickProvider(), user_timezone="Europe/Moscow")
    payload = json.loads(registry.execute_tool("list_projects", '{"query":"work"}'))
    assert [item["name"] for item in payload] == ["Work"]


def test_list_projects_tool_schema_does_not_require_id_or_name() -> None:
    registry = ToolRegistry(MockTickTickProvider(), user_timezone="Europe/Moscow")
    list_projects = next(
        tool["function"] for tool in registry.list_openrouter_tools() if tool["function"]["name"] == "list_projects"
    )
    assert "required" not in list_projects["parameters"]
    assert "id" not in list_projects["parameters"]["properties"]
    assert "name" not in list_projects["parameters"]["properties"]


def test_create_task_tool_schema_exposes_all_day_fields() -> None:
    registry = ToolRegistry(MockTickTickProvider(), user_timezone="Europe/Moscow")
    create_task = next(
        tool["function"] for tool in registry.list_openrouter_tools() if tool["function"]["name"] == "create_task"
    )
    assert "start_date" in create_task["parameters"]["properties"]
    assert "is_all_day" in create_task["parameters"]["properties"]
    assert "time_zone" in create_task["parameters"]["properties"]


def test_upcoming_tasks_excludes_overdue_and_undated_by_default() -> None:
    provider = MockTickTickProvider()
    provider.tasks = {
        "overdue": provider.tasks["task-2"].model_copy(
            update={
                "id": "overdue",
                "title": "old task",
                "project_id": "work",
                "project_name": "Work",
                "due_date": "2026-04-09T09:00:00+0000",
                "is_all_day": False,
                "time_zone": "Europe/Moscow",
            }
        ),
        "soon": provider.tasks["task-1"].model_copy(
            update={
                "id": "soon",
                "title": "soon task",
                "project_id": "inbox",
                "project_name": "Inbox",
                "due_date": "2026-04-25T10:00:00+0000",
                "is_all_day": False,
                "time_zone": "Europe/Moscow",
            }
        ),
        "later": provider.tasks["task-3"].model_copy(
            update={
                "id": "later",
                "title": "later task",
                "project_id": "personal",
                "project_name": "Personal",
                "due_date": "2026-05-04T00:00:00+0000",
                "is_all_day": True,
                "time_zone": "Europe/Moscow",
            }
        ),
        "nodue": provider.tasks["task-4"].model_copy(
            update={
                "id": "nodue",
                "title": "no due task",
                "project_id": "personal",
                "project_name": "Personal",
                "due_date": None,
            }
        ),
    }
    registry = ToolRegistry(
        provider,
        user_timezone="Europe/Moscow",
        now_provider=lambda: datetime(2026, 4, 24, 12, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    payload = json.loads(
        registry.execute_tool(
            "list_upcoming_tasks",
            json.dumps({"days": 30, "limit": 10, "include_overdue": False}, ensure_ascii=False),
        )
    )
    assert [item["title"] for item in payload] == ["soon task", "later task"]


def test_upcoming_tasks_can_append_undated_tasks_to_the_end() -> None:
    provider = MockTickTickProvider()
    provider.tasks = {
        "soon": provider.tasks["task-1"].model_copy(
            update={
                "id": "soon",
                "title": "soon task",
                "project_id": "inbox",
                "project_name": "Inbox",
                "due_date": "2026-04-25T10:00:00+0000",
                "is_all_day": False,
                "time_zone": "Europe/Moscow",
            }
        ),
        "nodue": provider.tasks["task-4"].model_copy(
            update={
                "id": "nodue",
                "title": "no due task",
                "project_id": "personal",
                "project_name": "Personal",
                "due_date": None,
            }
        ),
    }
    registry = ToolRegistry(
        provider,
        user_timezone="Europe/Moscow",
        now_provider=lambda: datetime(2026, 4, 24, 12, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    payload = json.loads(
        registry.execute_tool(
            "list_upcoming_tasks",
            json.dumps(
                {"days": 30, "limit": 10, "include_without_due_date": True},
                ensure_ascii=False,
            ),
        )
    )
    assert [item["title"] for item in payload] == ["soon task", "no due task"]


def test_due_date_human_for_tomorrow_contains_russian_relative_date_and_time() -> None:
    registry = ToolRegistry(
        MockTickTickProvider(),
        user_timezone="Europe/Moscow",
        now_provider=lambda: datetime(2026, 4, 24, 9, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    payload = registry._augment_task_payload(
        {
            "id": "task-1",
            "title": "timed task",
            "due_date": "2026-04-25T10:30:00+0000",
            "time_zone": "Europe/Moscow",
            "is_all_day": False,
        }
    )
    assert "завтра, 25 апреля" in payload["due_date_human"]
    assert "13:30" in payload["due_date_human"]


def test_due_date_human_for_all_day_contains_human_date() -> None:
    registry = ToolRegistry(
        MockTickTickProvider(),
        user_timezone="Europe/Moscow",
        now_provider=lambda: datetime(2026, 4, 24, 9, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    payload = registry._augment_task_payload(
        {
            "id": "task-2",
            "title": "all day task",
            "due_date": "2026-05-03T21:00:00+0000",
            "time_zone": "Europe/Moscow",
            "is_all_day": True,
        }
    )
    assert "4 мая" in payload["due_date_human"]


def test_due_date_human_marks_overdue_tasks() -> None:
    registry = ToolRegistry(
        MockTickTickProvider(),
        user_timezone="Europe/Moscow",
        now_provider=lambda: datetime(2026, 4, 24, 9, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    payload = registry._augment_task_payload(
        {
            "id": "task-3",
            "title": "old task",
            "due_date": "2026-04-09T09:00:00+0000",
            "time_zone": "Europe/Moscow",
            "is_all_day": False,
        }
    )
    assert "просрочено" in payload["due_date_human"]


def test_update_task_by_search_updates_unique_exact_title() -> None:
    provider = MockTickTickProvider()
    provider.tasks = {
        "task-1": provider.tasks["task-1"].model_copy(
            update={
                "title": "hello world",
                "project_id": "inbox",
                "project_name": "Inbox",
                "due_date": "2026-04-24T09:00:00+0000",
                "time_zone": "Europe/Moscow",
                "is_all_day": True,
            }
        )
    }
    registry = ToolRegistry(
        provider,
        user_timezone="Europe/Moscow",
        now_provider=lambda: datetime(2026, 4, 24, 12, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    payload = json.loads(
        registry.execute_tool(
            "update_task_by_search",
            json.dumps(
                {
                    "search": "hello world",
                    "fields": {"title": "hello world!"},
                    "exact_title": True,
                    "prefer_today": True,
                },
                ensure_ascii=False,
            ),
        )
    )
    assert payload["title"] == "hello world!"


def test_update_task_by_search_returns_not_found_without_asking_for_id() -> None:
    registry = ToolRegistry(MockTickTickProvider(), user_timezone="Europe/Moscow")
    payload = json.loads(
        registry.execute_tool(
            "update_task_by_search",
            json.dumps({"search": "missing", "fields": {"title": "x"}}, ensure_ascii=False),
        )
    )
    assert payload["not_found"] is True
    assert "task_id" not in payload["message"]


def test_update_task_by_search_returns_clarification_without_ids() -> None:
    provider = MockTickTickProvider()
    provider.tasks = {
        "task-1": provider.tasks["task-1"].model_copy(
            update={"title": "hello world", "project_name": "Inbox", "due_date": "2026-04-25T09:00:00+0000", "time_zone": "Europe/Moscow"}
        ),
        "task-2": provider.tasks["task-2"].model_copy(
            update={"title": "hello world", "project_name": "Work", "due_date": "2026-04-25T09:00:00+0000", "time_zone": "Europe/Moscow"}
        ),
    }
    registry = ToolRegistry(
        provider,
        user_timezone="Europe/Moscow",
        now_provider=lambda: datetime(2026, 4, 24, 12, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    payload = json.loads(
        registry.execute_tool(
            "update_task_by_search",
            json.dumps({"search": "hello world", "fields": {"title": "hello world!"}}, ensure_ascii=False),
        )
    )
    assert payload["needs_clarification"] is True
    assert payload["candidates"]
    assert all("id" not in item for item in payload["candidates"])


def test_upcoming_tasks_snapshot_like_output_contains_expected_fields() -> None:
    provider = MockTickTickProvider()
    provider.tasks = {
        "soon": provider.tasks["task-1"].model_copy(
            update={
                "id": "soon",
                "title": "soon task",
                "project_id": "inbox",
                "project_name": "Inbox",
                "due_date": "2026-04-25T10:00:00+0000",
                "is_all_day": False,
                "time_zone": "Europe/Moscow",
            }
        ),
        "nodue": provider.tasks["task-4"].model_copy(
            update={
                "id": "nodue",
                "title": "no due task",
                "project_id": "personal",
                "project_name": "Personal",
                "due_date": None,
            }
        ),
    }
    registry = ToolRegistry(
        provider,
        user_timezone="Europe/Moscow",
        now_provider=lambda: datetime(2026, 4, 24, 12, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    payload = json.loads(
        registry.execute_tool(
            "list_upcoming_tasks",
            json.dumps({"include_without_due_date": True}, ensure_ascii=False),
        )
    )
    for item in payload:
        assert "title" in item
        assert "project_id" in item
        assert "project_name" in item
        if item.get("due_date"):
            assert "due_date_display_date" in item
            assert "due_date_human" in item


def test_scenario_create_task_today_uses_all_day_fields_without_project_prompt() -> None:
    registry = ToolRegistry(MockTickTickProvider(), user_timezone="Europe/Moscow")
    payload = json.loads(
        registry.execute_tool(
            "create_task",
            json.dumps(
                {
                    "title": "hello world",
                    "due_date": "2026-04-24",
                    "is_all_day": True,
                    "time_zone": "Europe/Moscow",
                },
                ensure_ascii=False,
            ),
        )
    )
    assert payload["title"] == "hello world"
    assert payload["project_name"] == "Inbox"
    assert payload["is_all_day"] is True
    assert payload["time_zone"] == "Europe/Moscow"


def test_scenario_update_task_by_name_adds_exclamation_mark() -> None:
    provider = MockTickTickProvider()
    provider.tasks["task-1"] = provider.tasks["task-1"].model_copy(
        update={
            "title": "hello world",
            "project_id": "inbox",
            "project_name": "Inbox",
            "due_date": "2026-04-24T09:00:00+0000",
            "time_zone": "Europe/Moscow",
            "is_all_day": True,
        }
    )
    registry = ToolRegistry(
        provider,
        user_timezone="Europe/Moscow",
        now_provider=lambda: datetime(2026, 4, 24, 12, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    payload = json.loads(
        registry.execute_tool(
            "update_task_by_search",
            json.dumps(
                {
                    "search": "hello world",
                    "fields": {"title": "hello world!"},
                    "exact_title": True,
                    "prefer_today": True,
                },
                ensure_ascii=False,
            ),
        )
    )
    assert payload["title"] == "hello world!"


def test_scenario_two_matching_tasks_returns_short_clarification_payload_without_ids() -> None:
    provider = MockTickTickProvider()
    provider.tasks = {
        "task-1": provider.tasks["task-1"].model_copy(
            update={"title": "hello world", "project_name": "Inbox", "due_date": "2026-04-25T09:00:00+0000", "time_zone": "Europe/Moscow"}
        ),
        "task-2": provider.tasks["task-2"].model_copy(
            update={"title": "hello world", "project_name": "Work", "due_date": "2026-04-25T09:00:00+0000", "time_zone": "Europe/Moscow"}
        ),
    }
    registry = ToolRegistry(
        provider,
        user_timezone="Europe/Moscow",
        now_provider=lambda: datetime(2026, 4, 24, 12, 0, tzinfo=ZoneInfo("Europe/Moscow")),
    )
    payload = json.loads(
        registry.execute_tool(
            "update_task_by_search",
            json.dumps(
                {"search": "hello world", "fields": {"title": "hello world!"}},
                ensure_ascii=False,
            ),
        )
    )
    assert payload["needs_clarification"] is True
    assert len(payload["candidates"]) == 2
    assert all("id" not in candidate for candidate in payload["candidates"])

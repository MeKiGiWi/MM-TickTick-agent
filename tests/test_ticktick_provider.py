from __future__ import annotations

from typing import Any
import httpx

from app.domain.models import Project, Task, TickTickCredentials
from app.providers.ticktick.client import TickTickApiProvider
from app.services.provider_factory import build_ticktick_provider


def build_provider(**credentials_overrides: Any) -> TickTickApiProvider:
    payload = {
        "provider": "ticktick",
        "access_token": "token",
        "inbox_project_id": "inbox-123",
        **credentials_overrides,
    }
    credentials = TickTickCredentials(**payload)
    return TickTickApiProvider(credentials, user_timezone="Europe/Moscow")


def test_provider_has_no_guide_path_runtime_attribute() -> None:
    provider = build_provider()
    assert not hasattr(provider, "guide_path")


def test_provider_factory_builds_ticktick_provider_without_guide_path(tmp_path) -> None:
    credentials = TickTickCredentials(provider="ticktick", access_token="token")
    provider = build_ticktick_provider(credentials, tmp_path, user_timezone="Europe/Moscow")
    assert isinstance(provider, TickTickApiProvider)
    assert not hasattr(provider, "guide_path")


def test_task_model_accepts_real_ticktick_payload() -> None:
    task = Task.model_validate(
        {
            "id": "task-1",
            "title": "hello world",
            "projectId": "project-1",
            "projectName": "Inbox",
            "status": 2,
            "dueDate": "2026-04-24T08:00:00+0000",
            "startDate": "2026-04-24T06:00:00+0000",
            "isAllDay": True,
            "timeZone": "Europe/Moscow",
        }
    )
    assert task.project_id == "project-1"
    assert task.project_name == "Inbox"
    assert task.status == "completed"
    assert task.due_date == "2026-04-24T08:00:00+0000"
    assert task.start_date == "2026-04-24T06:00:00+0000"
    assert task.is_all_day is True
    assert task.time_zone == "Europe/Moscow"


def test_normalize_update_fields_maps_ticktick_date_aliases() -> None:
    normalized = TickTickApiProvider._normalize_update_fields(
        {
            "due_date": "2026-05-03T21:00:00+0000",
            "start_date": "2026-05-03T20:00:00+0000",
            "time_zone": "Europe/Moscow",
            "is_all_day": True,
        }
    )
    assert normalized == {
        "dueDate": "2026-05-03T21:00:00+0000",
        "startDate": "2026-05-03T20:00:00+0000",
        "timeZone": "Europe/Moscow",
        "isAllDay": True,
    }


def test_create_task_uses_documented_endpoint_and_default_inbox(monkeypatch) -> None:
    provider = build_provider()
    monkeypatch.setattr(
        provider,
        "_get_project_by_id",
        lambda project_id: Project(id=project_id, name="Inbox"),
    )
    recorded: dict[str, Any] = {}

    def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        recorded["method"] = method
        recorded["path"] = path
        recorded["json"] = kwargs["json"]
        return {
            "id": "task-1",
            "title": kwargs["json"]["title"],
            "projectId": kwargs["json"]["projectId"],
            "projectName": "Inbox",
            "status": 0,
        }

    monkeypatch.setattr(provider, "_request", fake_request)
    task = provider.create_task(title="hello world")
    assert task.project_id == "inbox-123"
    assert task.project_name == "Inbox"
    assert recorded == {
        "method": "POST",
        "path": "/task",
        "json": {
            "title": "hello world",
            "projectId": "inbox-123",
        },
    }


def test_create_task_preserves_resolved_project_id_when_response_omits_it(monkeypatch) -> None:
    provider = build_provider(inbox_project_id="inbox")
    monkeypatch.setattr(provider, "resolve_project_id", lambda project_id=None: "real-inbox")

    def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "id": "task-1",
            "title": kwargs["json"]["title"],
            "status": 0,
        }

    monkeypatch.setattr(provider, "_request", fake_request)
    monkeypatch.setattr(
        provider,
        "_get_project_by_id",
        lambda project_id: Project(id=project_id, name="Inbox"),
    )
    task = provider.create_task(title="hello world")
    assert task.project_id == "real-inbox"


def test_create_task_normalizes_all_day_local_date(monkeypatch) -> None:
    provider = build_provider()
    monkeypatch.setattr(
        provider,
        "_get_project_by_id",
        lambda project_id: Project(id=project_id, name="Inbox"),
    )
    recorded: dict[str, Any] = {}

    def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        recorded["json"] = kwargs["json"]
        return {
            "id": "task-1",
            "title": kwargs["json"]["title"],
            "projectId": kwargs["json"]["projectId"],
            "status": 0,
            "dueDate": kwargs["json"]["dueDate"],
            "timeZone": kwargs["json"]["timeZone"],
            "isAllDay": kwargs["json"]["isAllDay"],
        }

    monkeypatch.setattr(provider, "_request", fake_request)
    task = provider.create_task(
        title="hello world",
        due_date="2026-04-24",
        is_all_day=True,
        time_zone="Europe/Moscow",
    )
    assert task.due_date == "2026-04-23T21:00:00+0000"
    assert task.time_zone == "Europe/Moscow"
    assert task.is_all_day is True
    assert recorded["json"]["dueDate"] == "2026-04-23T21:00:00+0000"
    assert recorded["json"]["timeZone"] == "Europe/Moscow"
    assert recorded["json"]["isAllDay"] is True


def test_list_tasks_uses_filter_endpoint_for_all_open_tasks(monkeypatch) -> None:
    provider = build_provider()
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def fake_request(method: str, path: str, **kwargs: Any) -> list[dict[str, Any]]:
        calls.append((method, path, kwargs))
        return [
            {
                "id": "task-1",
                "title": "nearest task",
                "projectId": "project-1",
                "status": 0,
                "content": "important",
            }
        ]

    monkeypatch.setattr(provider, "_request", fake_request)
    monkeypatch.setattr(
        provider,
        "_get_project_by_id",
        lambda project_id: Project(id=project_id, name="Inbox"),
    )
    tasks = provider.list_tasks(search="nearest")
    assert [task.title for task in tasks] == ["nearest task"]
    assert calls == [("POST", "/task/filter", {"json": {"status": [0]}})]


def test_get_task_details_uses_project_scoped_endpoint(monkeypatch) -> None:
    provider = build_provider()
    provider._projects_cache["project-1"] = Project(id="project-1", name="Inbox")
    provider._task_project_cache["task-1"] = "project-1"
    recorded: list[tuple[str, str]] = []

    def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        recorded.append((method, path))
        return {
            "id": "task-1",
            "title": "hello",
            "projectId": "project-1",
            "status": 0,
        }

    monkeypatch.setattr(provider, "_request", fake_request)
    task = provider.get_task_details("task-1")
    assert task.project_id == "project-1"
    assert task.project_name == "Inbox"
    assert recorded == [("GET", "/project/project-1/task/task-1")]


def test_mark_complete_uses_completion_endpoint(monkeypatch) -> None:
    provider = build_provider()
    provider._projects_cache["project-1"] = Project(id="project-1", name="Inbox")
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def fake_request(method: str, path: str, **kwargs: Any) -> Any:
        calls.append((method, path, kwargs))
        if path == "/project/project-1/task/task-1/complete":
            return {}
        return {
            "id": "task-1",
            "title": "done",
            "projectId": "project-1",
            "status": 2,
        }

    monkeypatch.setattr(provider, "_request", fake_request)
    provider._task_project_cache["task-1"] = "project-1"
    task = provider.mark_complete("task-1")
    assert task.status == "completed"
    assert task.project_name == "Inbox"
    assert calls[1][0:2] == ("POST", "/project/project-1/task/task-1/complete")


def test_move_task_sends_from_project_id(monkeypatch) -> None:
    provider = build_provider()
    provider._projects_cache["project-1"] = Project(id="project-1", name="Inbox")
    provider._projects_cache["project-2"] = Project(id="project-2", name="Work")
    calls: list[tuple[str, str, dict[str, Any]]] = []

    def fake_request(method: str, path: str, **kwargs: Any) -> Any:
        calls.append((method, path, kwargs))
        if path == "/task/move":
            return [{"id": "task-1", "etag": "etag"}]
        return {
            "id": "task-1",
            "title": "moved",
            "projectId": "project-2",
            "status": 0,
        }

    monkeypatch.setattr(provider, "_request", fake_request)
    provider._task_project_cache["task-1"] = "project-1"
    task = provider.move_task("task-1", "project-2")
    assert task.project_id == "project-2"
    assert task.project_name == "Work"
    move_call = next(call for call in calls if call[1] == "/task/move")
    assert move_call == (
        "POST",
        "/task/move",
        {
            "json": [
                {
                    "fromProjectId": "project-1",
                    "toProjectId": "project-2",
                    "taskId": "task-1",
                }
            ]
        },
    )


def test_list_projects_keeps_configured_inbox_context(monkeypatch) -> None:
    provider = build_provider()

    def fake_request(method: str, path: str, **kwargs: Any) -> Any:
        if path == "/project":
            return [{"id": "work", "name": "Work", "kind": "TASK"}]
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(provider, "_request", fake_request)

    def fake_get_project(project_id: str) -> Project:
        request = httpx.Request("GET", f"https://api.ticktick.com/open/v1/project/{project_id}")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("missing from list", request=request, response=response)

    monkeypatch.setattr(provider, "_get_project_by_id", fake_get_project)
    projects = provider.list_projects()
    assert [project.id for project in projects] == ["work", "inbox-123"]
    assert projects[-1].name == "Inbox (configured)"


def test_list_projects_tolerates_invalid_configured_project_lookup(monkeypatch) -> None:
    provider = build_provider(inbox_project_id="inbox-123")

    def fake_request(method: str, path: str, **kwargs: Any) -> Any:
        if path == "/project":
            return [{"id": "work", "name": "Work", "kind": "TASK"}]
        if path == "/project/inbox-123":
            return [{"unexpected": True}]
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(provider, "_request", fake_request)
    projects = provider.list_projects()
    assert [project.id for project in projects] == ["work", "inbox-123"]
    assert projects[-1].name == "Inbox (configured)"


def test_list_tasks_attaches_project_name(monkeypatch) -> None:
    provider = build_provider()

    def fake_request(method: str, path: str, **kwargs: Any) -> list[dict[str, Any]]:
        if path == "/task/filter":
            return [
                {
                    "id": "task-1",
                    "title": "nearest task",
                    "projectId": "project-1",
                    "status": 0,
                }
            ]
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(provider, "_request", fake_request)
    monkeypatch.setattr(
        provider,
        "_get_project_by_id",
        lambda project_id: Project(id=project_id, name="Inbox"),
    )
    tasks = provider.list_tasks()
    assert tasks[0].project_name == "Inbox"


def test_resolve_default_project_id_falls_back_from_literal_inbox(monkeypatch) -> None:
    provider = build_provider(inbox_project_id="inbox")

    def fake_get_project(project_id: str) -> Project:
        request = httpx.Request("GET", f"https://api.ticktick.com/open/v1/project/{project_id}")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("missing", request=request, response=response)

    monkeypatch.setattr(provider, "_get_project_by_id", fake_get_project)
    monkeypatch.setattr(
        provider,
        "_load_projects",
        lambda: [
            Project(id="p1", name="Inbox", kind="TASK"),
            Project(id="p2", name="Work", kind="TASK"),
        ],
    )
    assert provider.resolve_default_project_id() == "p1"


def test_create_task_uses_real_project_id_when_configured_inbox_is_literal(monkeypatch) -> None:
    provider = build_provider(inbox_project_id="inbox")
    recorded: dict[str, Any] = {}

    def fake_get_project(project_id: str) -> Project:
        request = httpx.Request("GET", f"https://api.ticktick.com/open/v1/project/{project_id}")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("missing", request=request, response=response)

    def fake_request(method: str, path: str, **kwargs: Any) -> Any:
        if path == "/project":
            return [
                {"id": "real-inbox", "name": "Inbox", "kind": "TASK"},
                {"id": "work", "name": "Work", "kind": "TASK"},
            ]
        if path == "/task":
            recorded["json"] = kwargs["json"]
            return {
                "id": "task-1",
                "title": kwargs["json"]["title"],
                "projectId": kwargs["json"]["projectId"],
                "status": 0,
            }
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(provider, "_get_project_by_id", fake_get_project)
    monkeypatch.setattr(provider, "_request", fake_request)
    task = provider.create_task(title="hello world")
    assert task.project_id == "real-inbox"
    assert recorded["json"]["projectId"] == "real-inbox"


def test_create_subtasks_after_create_task_uses_parent_project_automatically(monkeypatch) -> None:
    provider = build_provider()
    created_payloads: list[dict[str, Any]] = []

    def fake_request(method: str, path: str, **kwargs: Any) -> Any:
        if path == "/task" and kwargs["json"].get("parentId") is None:
            return {
                "id": "task-parent",
                "title": kwargs["json"]["title"],
                "projectId": "project-42",
                "status": 0,
            }
        if path == "/project/project-42/task/task-parent":
            return {
                "id": "task-parent",
                "title": "Parent",
                "projectId": "project-42",
                "status": 0,
            }
        if path == "/task":
            created_payloads.append(kwargs["json"])
            return {
                "id": f"sub-{len(created_payloads)}",
                "title": kwargs["json"]["title"],
                "projectId": kwargs["json"]["projectId"],
                "parentId": kwargs["json"]["parentId"],
                "status": 0,
            }
        raise AssertionError(f"Unexpected request: {method} {path}")

    monkeypatch.setattr(provider, "_request", fake_request)
    monkeypatch.setattr(provider, "resolve_project_id", lambda project_id=None: "project-42")
    monkeypatch.setattr(
        provider,
        "_get_project_by_id",
        lambda project_id: Project(id=project_id, name="Inbox"),
    )

    parent = provider.create_task(title="Parent")
    subtasks = provider.create_subtasks(parent.id, ["One", "Two"])

    assert [item.parent_id for item in subtasks] == [parent.id, parent.id]
    assert [payload["projectId"] for payload in created_payloads] == ["project-42", "project-42"]


def test_create_task_with_subtasks_returns_parent_and_subtasks(monkeypatch) -> None:
    provider = build_provider()
    parent = Task(id="task-parent", title="Parent", project_id="project-1")
    subtasks = [
        Task(id="sub-1", title="One", project_id="project-1", parent_id="task-parent"),
        Task(id="sub-2", title="Two", project_id="project-1", parent_id="task-parent"),
    ]
    monkeypatch.setattr(provider, "create_task", lambda **kwargs: parent)
    monkeypatch.setattr(provider, "create_subtasks", lambda task_id, titles: subtasks)

    payload = provider.create_task_with_subtasks(title="Parent", subtask_titles=["One", "Two"])

    assert payload["task"] == parent
    assert payload["subtasks"] == subtasks


def test_resolve_default_project_id_falls_back_when_configured_id_raises_value_error(
    monkeypatch,
) -> None:
    provider = build_provider(inbox_project_id="inbox")

    monkeypatch.setattr(
        provider,
        "_validated_project_id",
        lambda project_id: (_ for _ in ()).throw(ValueError("bad")),
    )
    monkeypatch.setattr(
        provider,
        "_load_projects",
        lambda: [
            Project(id="real-inbox", name="Inbox", kind="TASK"),
            Project(id="work", name="Work", kind="TASK"),
        ],
    )

    assert provider.resolve_default_project_id() == "real-inbox"


def test_resolve_target_project_id_treats_inbox_alias_as_default(monkeypatch) -> None:
    provider = build_provider(inbox_project_id="inbox")
    monkeypatch.setattr(provider, "resolve_default_project_id", lambda: "real-inbox")

    assert provider.resolve_project_id("inbox") == "real-inbox"
    assert provider.resolve_project_id("Входящие") == "real-inbox"


def test_request_error_keeps_status_endpoint_and_body(monkeypatch) -> None:
    provider = build_provider()

    def fake_client_request(method: str, path: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request(method, f"https://api.ticktick.com/open/v1{path}")
        return httpx.Response(400, request=request, text='{"error":"bad request"}')

    monkeypatch.setattr(provider.client, "request", fake_client_request)
    try:
        provider._request("POST", "/task", json={"title": "x"})
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ValueError")
    assert "TickTick API error 400 POST /task" in message
    assert '{"error":"bad request"}' in message


def test_request_retries_and_recovers_from_temporary_network_error(monkeypatch) -> None:
    provider = build_provider()
    calls = {"count": 0}

    def fake_client_request(method: str, path: str, **kwargs: Any) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            request = httpx.Request(method, f"https://api.ticktick.com/open/v1{path}")
            raise httpx.ConnectError("Temporary failure in name resolution", request=request)
        request = httpx.Request(method, f"https://api.ticktick.com/open/v1{path}")
        return httpx.Response(200, request=request, json={"ok": True})

    monkeypatch.setattr(provider.client, "request", fake_client_request)
    monkeypatch.setattr(provider.client, "close", lambda: None)
    monkeypatch.setattr(provider, "_build_client", lambda: provider.client)
    payload = provider._request("GET", "/project")
    assert payload == {"ok": True}
    assert calls["count"] == 2


def test_request_wraps_network_errors_into_human_readable_value_error(monkeypatch) -> None:
    provider = build_provider()

    def fake_client_request(method: str, path: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request(method, f"https://api.ticktick.com/open/v1{path}")
        raise httpx.ConnectError("nodename nor servname provided, or not known", request=request)

    monkeypatch.setattr(provider.client, "request", fake_client_request)
    monkeypatch.setattr(provider.client, "close", lambda: None)
    monkeypatch.setattr(provider, "_build_client", lambda: provider.client)
    try:
        provider._request("GET", "/project")
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ValueError")
    assert "TickTick network error during GET /project" in message
    assert "DNS" in message


def test_update_task_sends_safe_full_payload(monkeypatch) -> None:
    provider = build_provider()
    current = Task(
        id="task-1",
        title="hello world",
        project_id="project-1",
        project_name="Inbox",
        content="body",
        due_date="2026-04-24T10:30:00+0000",
        start_date="2026-04-24T09:30:00+0000",
        is_all_day=True,
        time_zone="Europe/Moscow",
        priority=3,
    )
    monkeypatch.setattr(provider, "get_task_details", lambda task_id: current)
    recorded: dict[str, Any] = {}

    def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        recorded["json"] = kwargs["json"]
        return {
            "id": "task-1",
            "title": kwargs["json"]["title"],
            "projectId": kwargs["json"]["projectId"],
            "status": 0,
            "dueDate": kwargs["json"]["dueDate"],
            "startDate": kwargs["json"]["startDate"],
            "isAllDay": kwargs["json"]["isAllDay"],
            "timeZone": kwargs["json"]["timeZone"],
            "priority": kwargs["json"]["priority"],
            "content": kwargs["json"]["content"],
        }

    monkeypatch.setattr(provider, "_request", fake_request)
    task = provider.update_task("task-1", {"title": "hello world!"})
    assert task.title == "hello world!"
    assert recorded["json"]["id"] == "task-1"
    assert recorded["json"]["projectId"] == "project-1"
    assert recorded["json"]["title"] == "hello world!"
    assert recorded["json"]["dueDate"] == "2026-04-24T10:30:00+0000"
    assert recorded["json"]["startDate"] == "2026-04-24T09:30:00+0000"
    assert recorded["json"]["isAllDay"] is True
    assert recorded["json"]["timeZone"] == "Europe/Moscow"

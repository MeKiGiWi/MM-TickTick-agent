from __future__ import annotations

from typing import Any

import httpx

from app.domain.models import Project, Task, TickTickCredentials
from app.providers.ticktick.client import TickTickApiProvider


def build_provider(**credentials_overrides: Any) -> TickTickApiProvider:
    payload = {
        "provider": "ticktick",
        "access_token": "token",
        "inbox_project_id": "inbox-123",
        **credentials_overrides,
    }
    credentials = TickTickCredentials(**payload)
    return TickTickApiProvider(credentials)


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
    assert provider._resolve_default_project_id() == "p1"

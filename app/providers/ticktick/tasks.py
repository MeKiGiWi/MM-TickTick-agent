from typing import Any, Callable, Optional

from app.domain.models import Task
from app.providers.ticktick.api import TickTickApiClient
from app.providers.ticktick.dates import (
    normalize_completion_status,
    normalize_status_filter,
    normalize_task_datetime_fields,
)
from app.providers.ticktick.mapper import TickTickTaskMapper
from app.providers.ticktick.projects import TickTickProjectsService


class TickTickTasksService:
    def __init__(
        self,
        api: TickTickApiClient,
        projects: TickTickProjectsService,
        mapper: TickTickTaskMapper,
        default_timezone_name: Callable[[], str],
    ) -> None:
        self.api = api
        self.projects = projects
        self.mapper = mapper
        self.default_timezone_name = default_timezone_name
        self.task_project_cache: dict[str, str] = {}

    def remember_task(self, task: Task) -> Task:
        self.task_project_cache[task.id] = task.project_id
        self.projects.remember_default_project_id(task.project_id)
        return task

    def map_task(self, payload: dict[str, Any]) -> Task:
        return self.remember_task(self.mapper.task_from_payload(payload))

    @staticmethod
    def normalize_update_fields(fields: dict[str, object]) -> dict[str, object]:
        normalized: dict[str, object] = {}
        for key, value in fields.items():
            if key in {"project_id", "projectId"}:
                normalized["projectId"] = value
            elif key in {"due_date", "dueDate"}:
                normalized["dueDate"] = value
            elif key in {"start_date", "startDate"}:
                normalized["startDate"] = value
            elif key in {"time_zone", "timeZone"}:
                normalized["timeZone"] = value
            elif key in {"is_all_day", "isAllDay"}:
                normalized["isAllDay"] = value
            elif key in {"title", "content", "priority", "status"}:
                normalized[key] = value
            else:
                normalized[key] = value
        return normalized

    def normalize_task_datetime_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        return normalize_task_datetime_fields(payload, self.default_timezone_name())

    def search_task_project_id(self, task_id: str) -> Optional[str]:
        cached = self.task_project_cache.get(task_id)
        if cached:
            return cached

        projects = self.projects.load_projects()
        for project in projects:
            payload = self.api.request("GET", f"/project/{project.id}/data")
            for item in payload.get("tasks", []):
                task = self.map_task(item)
                if task.id == task_id:
                    return task.project_id

        if projects:
            completed = self.api.request(
                "POST",
                "/task/completed",
                json={"projectIds": [project.id for project in projects]},
            )
            for item in completed:
                task = self.map_task(item)
                if task.id == task_id:
                    return task.project_id
        return None

    def get_task_details(self, task_id: str, project_id: Optional[str] = None) -> Task:
        resolved_project_id = project_id or self.search_task_project_id(task_id)
        if not resolved_project_id:
            raise ValueError(
                f"Не удалось определить project_id для задачи '{task_id}'. Сначала откройте список задач или укажите проект."
            )
        return self.map_task(
            self.api.request("GET", f"/project/{resolved_project_id}/task/{task_id}")
        )

    def create_task(
        self,
        *,
        title: str,
        project_id: Optional[str] = None,
        content: Optional[str] = None,
        due_date: Optional[str] = None,
        start_date: Optional[str] = None,
        is_all_day: Optional[bool] = None,
        time_zone: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> Task:
        resolved_project_id = self.projects.resolve_project_id(project_id)
        payload: dict[str, Any] = {"title": title, "projectId": resolved_project_id}
        if content:
            payload["content"] = content
        if due_date:
            payload["dueDate"] = due_date
        if start_date:
            payload["startDate"] = start_date
        if is_all_day is not None:
            payload["isAllDay"] = is_all_day
        if time_zone:
            payload["timeZone"] = time_zone
        if priority is not None:
            payload["priority"] = priority
        response = self.api.request(
            "POST", "/task", json=self.normalize_task_datetime_fields(payload)
        )
        if isinstance(response, dict) and not response.get("projectId"):
            response = {**response, "projectId": resolved_project_id}
        return self.map_task(response)

    def list_tasks(
        self,
        *,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[Task]:
        normalized_status = normalize_status_filter(status)
        resolved_project_id = self.projects.resolve_project_id(project_id) if project_id else None

        if normalized_status == "completed":
            payload: dict[str, Any] = {}
            if resolved_project_id:
                payload["projectIds"] = [resolved_project_id]
            tasks_payload = self.api.request("POST", "/task/completed", json=payload)
        elif resolved_project_id:
            tasks_payload = self.api.request("GET", f"/project/{resolved_project_id}/data").get(
                "tasks", []
            )
        else:
            tasks_payload = self.api.request("POST", "/task/filter", json={"status": [0]})

        items = [self.map_task(item) for item in tasks_payload]
        if normalized_status:
            items = [task for task in items if task.status == normalized_status]
        if search:
            lowered = search.lower()
            items = [
                task
                for task in items
                if lowered in task.title.lower() or lowered in (task.content or "").lower()
            ]
        return items

    def create_subtasks(self, task_id: str, titles: list[str]) -> list[Task]:
        parent = self.get_task_details(task_id)
        created: list[Task] = []
        for title in titles:
            payload = {"title": title, "projectId": parent.project_id, "parentId": parent.id}
            response = self.api.request("POST", "/task", json=payload)
            if isinstance(response, dict):
                response = {
                    **response,
                    "projectId": response.get("projectId") or parent.project_id,
                    "parentId": response.get("parentId") or parent.id,
                }
            created.append(self.map_task(response))
        return created

    def create_task_with_subtasks(self, **kwargs: Any) -> dict[str, object]:
        create_kwargs = dict(kwargs)
        subtask_titles = list(create_kwargs.pop("subtask_titles", []))
        task = self.create_task(**create_kwargs)
        subtasks = self.create_subtasks(task.id, subtask_titles)
        return {"task": task, "subtasks": subtasks}

    def move_task(self, task_id: str, project_id: str) -> Task:
        resolved_project_id = self.projects.resolve_project_id(project_id)
        current = self.get_task_details(task_id)
        if current.parent_id:
            raise ValueError(
                "Нельзя переместить подзадачу отдельно от родительской задачи, переместите родительскую задачу."
            )
        current_project_id = current.project_id
        subtasks = list(current.subtasks)
        if not subtasks:
            subtasks = [
                task
                for task in self.list_tasks(project_id=current_project_id)
                if task.parent_id == current.id
            ]
        move_items = [
            {
                "fromProjectId": current_project_id,
                "toProjectId": resolved_project_id,
                "taskId": item.id,
            }
            for item in [current, *subtasks]
        ]
        self.api.request("POST", "/task/move", json=move_items)
        for item in [current, *subtasks]:
            self.task_project_cache[item.id] = resolved_project_id
        return self.get_task_details(task_id, project_id=resolved_project_id)

    def mark_complete(self, task_id: str) -> Task:
        current = self.get_task_details(task_id)
        self.api.request("POST", f"/project/{current.project_id}/task/{task_id}/complete")
        return self.get_task_details(task_id, project_id=current.project_id)

    def update_task(self, task_id: str, fields: dict[str, object]) -> Task:
        normalized_fields = self.normalize_update_fields(fields)
        status = normalized_fields.pop("status", None)
        target_project_id: Optional[str] = None
        if "projectId" in normalized_fields:
            target_project_id = self.projects.resolve_project_id(
                str(normalized_fields.pop("projectId"))
            )

        current = self.get_task_details(task_id)
        updated = current
        if normalized_fields:
            merged_task = current.model_copy(
                update={
                    "project_id": current.project_id,
                    "title": normalized_fields.get("title", current.title),
                    "content": normalized_fields.get("content", current.content),
                    "due_date": normalized_fields.get("dueDate", current.due_date),
                    "start_date": normalized_fields.get("startDate", current.start_date),
                    "is_all_day": normalized_fields.get("isAllDay", current.is_all_day),
                    "time_zone": normalized_fields.get("timeZone", current.time_zone),
                    "priority": normalized_fields.get("priority", current.priority),
                }
            )
            payload = self.normalize_task_datetime_fields(
                self.mapper.build_task_update_payload(merged_task)
            )
            updated = self.map_task(self.api.request("POST", f"/task/{task_id}", json=payload))

        if target_project_id is not None:
            updated = self.move_task(task_id, target_project_id)

        if status is not None:
            normalize_completion_status(status)
            updated = self.mark_complete(task_id)

        return updated

from typing import Any, Callable, Optional

from app.domain.models import Task


class TickTickTaskMapper:
    def __init__(
        self, project_name_resolver: Optional[Callable[[str], Optional[str]]] = None
    ) -> None:
        self.project_name_resolver = project_name_resolver

    def task_from_payload(self, payload: dict[str, Any]) -> Task:
        task = Task.model_validate(payload)
        if self.project_name_resolver:
            task.project_name = self.project_name_resolver(task.project_id)
        return task

    @staticmethod
    def build_task_update_payload(task: Task) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": task.id,
            "projectId": task.project_id,
            "title": task.title,
            "priority": task.priority,
        }
        if task.parent_id:
            payload["parentId"] = task.parent_id
        if task.content is not None:
            payload["content"] = task.content
        if task.due_date:
            payload["dueDate"] = task.due_date
        if task.start_date:
            payload["startDate"] = task.start_date
        if task.time_zone:
            payload["timeZone"] = task.time_zone
        if task.is_all_day:
            payload["isAllDay"] = True
        return payload

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import httpx

from app.domain.models import Project, Task, TickTickCredentials
from app.providers.ticktick.base import TickTickProvider


class TickTickApiProvider(TickTickProvider):
    def __init__(
        self,
        credentials: TickTickCredentials,
        guide_path: Optional[Path] = None,
    ) -> None:
        self.credentials = credentials
        self.guide_path = guide_path
        self.base_url = "https://api.ticktick.com/open/v1"
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {credentials.access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )
        self._task_project_cache: dict[str, str] = {}
        self._projects_cache: dict[str, Project] = {}

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    @staticmethod
    def _normalize_status_filter(status: Optional[str]) -> Optional[str]:
        if status is None:
            return None
        normalized = status.lower()
        if normalized in {"normal", "open"}:
            return "normal"
        if normalized in {"completed", "done"}:
            return "completed"
        raise ValueError(f"Неподдерживаемый статус задач: {status}")

    def _remember_task(self, task: Task) -> Task:
        self._task_project_cache[task.id] = task.project_id
        return task

    def _normalize_task(self, payload: dict[str, Any]) -> Task:
        return self._remember_task(Task.model_validate(payload))

    def _load_projects(self) -> list[Project]:
        projects = [Project.model_validate(item) for item in self._request("GET", "/project")]
        self._projects_cache = {project.id: project for project in projects}
        return projects

    def _get_project_by_id(self, project_id: str) -> Project:
        if project_id in self._projects_cache:
            return self._projects_cache[project_id]
        project = Project.model_validate(self._request("GET", f"/project/{project_id}"))
        self._projects_cache[project.id] = project
        return project

    def _validated_project_id(self, project_id: str) -> str:
        self._get_project_by_id(project_id)
        return project_id

    def _resolve_default_project_id(self) -> str:
        configured = (self.credentials.inbox_project_id or "").strip()
        if configured:
            try:
                return self._validated_project_id(configured)
            except httpx.HTTPStatusError:
                pass

        projects = self._load_projects()
        if projects:
            return projects[0].id
        raise ValueError(
            "Не удалось определить project_id для новой задачи: inbox/default project не настроен или недоступен."
        )

    def _resolve_target_project_id(self, project_id: Optional[str]) -> str:
        target = (project_id or "").strip()
        if target:
            return self._validated_project_id(target)
        return self._resolve_default_project_id()

    def _search_task_project_id(self, task_id: str) -> Optional[str]:
        cached = self._task_project_cache.get(task_id)
        if cached:
            return cached

        projects = self._load_projects()
        for project in projects:
            payload = self._request("GET", f"/project/{project.id}/data")
            for item in payload.get("tasks", []):
                task = self._normalize_task(item)
                if task.id == task_id:
                    return task.project_id

        if projects:
            completed = self._request(
                "POST",
                "/task/completed",
                json={"projectIds": [project.id for project in projects]},
            )
            for item in completed:
                task = self._normalize_task(item)
                if task.id == task_id:
                    return task.project_id
        return None

    def _get_task_details(self, task_id: str, project_id: Optional[str] = None) -> Task:
        resolved_project_id = project_id or self._search_task_project_id(task_id)
        if not resolved_project_id:
            raise ValueError(
                f"Не удалось определить project_id для задачи '{task_id}'. Сначала откройте список задач или укажите проект."
            )
        return self._normalize_task(
            self._request("GET", f"/project/{resolved_project_id}/task/{task_id}")
        )

    @staticmethod
    def _normalize_update_fields(fields: dict[str, object]) -> dict[str, object]:
        normalized: dict[str, object] = {}
        for key, value in fields.items():
            if key == "project_id":
                normalized["projectId"] = value
            elif key == "due_date":
                normalized["dueDate"] = value
            elif key == "start_date":
                normalized["startDate"] = value
            elif key == "status":
                if value in {"normal", "open"}:
                    normalized["status"] = 0
                elif value in {"completed", "done"}:
                    normalized["status"] = 2
                else:
                    normalized["status"] = value
            else:
                normalized[key] = value
        return normalized

    def create_task(
        self,
        *,
        title: str,
        project_id: Optional[str] = None,
        content: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> Task:
        payload: dict[str, Any] = {
            "title": title,
            "projectId": self._resolve_target_project_id(project_id),
        }
        if content:
            payload["content"] = content
        if due_date:
            payload["dueDate"] = due_date
        if priority is not None:
            payload["priority"] = priority
        return self._normalize_task(self._request("POST", "/task", json=payload))

    def list_tasks(
        self,
        *,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[Task]:
        normalized_status = self._normalize_status_filter(status)
        tasks_payload: list[dict[str, Any]]

        if normalized_status == "completed":
            payload: dict[str, Any] = {}
            if project_id:
                payload["projectIds"] = [project_id]
            tasks_payload = self._request("POST", "/task/completed", json=payload)
        elif project_id:
            tasks_payload = self._request("GET", f"/project/{project_id}/data").get("tasks", [])
        else:
            payload = {"status": [0]}
            tasks_payload = self._request("POST", "/task/filter", json=payload)

        items = [self._normalize_task(item) for item in tasks_payload]
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

    def get_task_details(self, task_id: str) -> Task:
        return self._get_task_details(task_id)

    def create_subtasks(self, task_id: str, titles: list[str]) -> list[Task]:
        parent = self.get_task_details(task_id)
        created: list[Task] = []
        for title in titles:
            payload = {
                "title": title,
                "projectId": parent.project_id,
                "parentId": parent.id,
            }
            created.append(self._normalize_task(self._request("POST", "/task", json=payload)))
        return created

    def update_task(self, task_id: str, fields: dict[str, object]) -> Task:
        current = self.get_task_details(task_id)
        payload = {
            "id": current.id,
            "projectId": current.project_id,
            **self._normalize_update_fields(fields),
        }
        return self._normalize_task(self._request("POST", f"/task/{task_id}", json=payload))

    def list_projects(self) -> list[Project]:
        projects = self._load_projects()
        configured = (self.credentials.inbox_project_id or "").strip()
        if configured and configured not in {project.id for project in projects}:
            try:
                projects.append(self._get_project_by_id(configured))
            except httpx.HTTPStatusError:
                projects.append(Project(id=configured, name="Inbox (configured)", kind="TASK"))
        return projects

    def move_task(self, task_id: str, project_id: str) -> Task:
        current_project_id = self._task_project_cache.get(task_id)
        if not current_project_id:
            current_project_id = self.get_task_details(task_id).project_id
        self._request(
            "POST",
            "/task/move",
            json=[
                {
                    "fromProjectId": current_project_id,
                    "toProjectId": project_id,
                    "taskId": task_id,
                }
            ],
        )
        self._task_project_cache[task_id] = project_id
        return self._get_task_details(task_id, project_id=project_id)

    def mark_complete(self, task_id: str) -> Task:
        current = self.get_task_details(task_id)
        self._request("POST", f"/project/{current.project_id}/task/{task_id}/complete")
        return self._get_task_details(task_id, project_id=current.project_id)

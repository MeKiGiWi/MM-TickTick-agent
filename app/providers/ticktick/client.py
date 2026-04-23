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

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()

    def list_tasks(
        self,
        *,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[Task]:
        payload: dict[str, Any] = {}
        if project_id:
            tasks = self._request("GET", f"/project/{project_id}/data").get("tasks", [])
        else:
            tasks = self._request("GET", "/project/all/data").get("tasks", [])
        items = [Task.model_validate(item) for item in tasks]
        if status:
            items = [task for task in items if task.status == status]
        if search:
            lowered = search.lower()
            items = [task for task in items if lowered in task.title.lower()]
        return items

    def get_task_details(self, task_id: str) -> Task:
        return Task.model_validate(self._request("GET", f"/task/{task_id}"))

    def create_subtasks(self, task_id: str, titles: list[str]) -> list[Task]:
        parent = self.get_task_details(task_id)
        created: list[Task] = []
        for title in titles:
            payload = {
                "title": title,
                "projectId": parent.project_id,
                "parentId": parent.id,
            }
            created.append(Task.model_validate(self._request("POST", "/task", json=payload)))
        return created

    def update_task(self, task_id: str, fields: dict[str, object]) -> Task:
        current = self.get_task_details(task_id)
        payload = {
            "id": current.id,
            "projectId": current.project_id,
            **fields,
        }
        return Task.model_validate(self._request("POST", f"/task/{task_id}", json=payload))

    def list_projects(self) -> list[Project]:
        return [Project.model_validate(item) for item in self._request("GET", "/project")]

    def move_task(self, task_id: str, project_id: str) -> Task:
        self._request(
            "POST",
            "/batch/taskProject",
            json=[{"fromProjectId": "", "toProjectId": project_id, "taskId": task_id}],
        )
        return self.get_task_details(task_id)

    def mark_complete(self, task_id: str) -> Task:
        return self.update_task(task_id, {"status": "completed"})

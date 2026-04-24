from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from app.providers.ticktick.base import TickTickProvider
from app.tools.presenter import ToolPresenter
from app.tools.task_search import TaskSearch


class ToolHandlers:
    def __init__(
        self,
        provider: TickTickProvider,
        presenter: ToolPresenter,
        task_search: TaskSearch,
    ) -> None:
        self.provider = provider
        self.presenter = presenter
        self.task_search = task_search

    @staticmethod
    def build_update_fields(payload: dict[str, Any]) -> dict[str, Any]:
        editable_fields = (
            "title",
            "content",
            "due_date",
            "start_date",
            "is_all_day",
            "time_zone",
            "priority",
            "status",
            "project_id",
        )
        return {
            key: payload[key]
            for key in editable_fields
            if key in payload and payload[key] is not None
        }

    def create_task(self, **kwargs: Any) -> Any:
        return self.provider.create_task(**kwargs)

    def create_task_with_subtasks(self, **kwargs: Any) -> Any:
        return self.provider.create_task_with_subtasks(**kwargs)

    def list_tasks(self, **kwargs: Any) -> Any:
        return self.provider.list_tasks(**kwargs)

    def get_task_details(self, task_id: str, **_: Any) -> Any:
        return self.provider.get_task_details(task_id)

    def create_subtasks(self, task_id: str, titles: list[str], **_: Any) -> Any:
        return self.provider.create_subtasks(task_id=task_id, titles=titles)

    def update_task(self, task_id: str, **payload: Any) -> Any:
        fields = self.build_update_fields(payload)
        if not fields:
            return {
                "error": {
                    "tool": "update_task",
                    "message": "Не переданы поля для обновления задачи.",
                }
            }
        return self.provider.update_task(task_id=task_id, fields=fields)

    def update_task_by_search(
        self,
        search: str,
        prefer_due_date: Optional[str] = None,
        prefer_today: bool = False,
        exact_title: bool = False,
        **payload: Any,
    ) -> Any:
        fields = self.build_update_fields(payload)
        if not fields:
            return {
                "error": {
                    "tool": "update_task_by_search",
                    "message": "Не переданы поля для обновления задачи.",
                }
            }
        return self.task_search.update_task_by_search(
            fields=fields,
            search=search,
            prefer_due_date=prefer_due_date,
            prefer_today=prefer_today,
            exact_title=exact_title,
            search_project_id=payload.get("search_project_id"),
        )

    def list_projects(self, query: Optional[str] = None, **_: Any) -> list[Any]:
        projects = self.provider.list_projects()
        return [
            project
            for project in projects
            if self.task_search.project_matches_query(project, query)
        ]

    def list_upcoming_tasks(
        self,
        days: int = 30,
        limit: int = 10,
        include_overdue: bool = False,
        include_without_due_date: bool = False,
        project_id: Optional[str] = None,
        **_: Any,
    ) -> list[dict[str, Any]]:
        tasks = self.provider.list_tasks(status="normal", project_id=project_id)
        today = self.presenter._now().date()
        cutoff = today + timedelta(days=max(days, 0))
        dated: list[dict[str, Any]] = []
        undated: list[dict[str, Any]] = []
        for task in tasks:
            payload = self.presenter.present(task)
            due_date_display = payload.get("due_date_display_date")
            if not isinstance(due_date_display, str):
                if include_without_due_date:
                    undated.append(payload)
                continue
            due_day = date.fromisoformat(due_date_display)
            if not include_overdue and due_day < today:
                continue
            if due_day > cutoff:
                continue
            dated.append(payload)

        dated.sort(
            key=lambda item: (
                item.get("due_date_display_date"),
                item.get("due_date_display_time") is None,
                item.get("due_date_display_time") or "",
                item.get("title") or "",
            )
        )
        undated.sort(key=lambda item: item.get("title") or "")
        result = dated + undated if include_without_due_date else dated
        return result[: max(limit, 0)]

    def move_task(self, task_id: str, project_id: str, **_: Any) -> Any:
        return self.provider.move_task(task_id=task_id, project_id=project_id)

    def mark_complete(self, task_id: str, **_: Any) -> Any:
        return self.provider.mark_complete(task_id)

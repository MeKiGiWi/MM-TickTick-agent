from __future__ import annotations

from typing import Any, Optional

from app.providers.ticktick.base import TickTickProvider
from app.tools.presenter import ToolPresenter


class TaskSearch:
    def __init__(
        self,
        provider: TickTickProvider,
        presenter: ToolPresenter,
        *,
        now_provider: Optional[callable] = None,
    ) -> None:
        self.provider = provider
        self.presenter = presenter
        self.now_provider = now_provider

    def project_matches_query(self, item: Any, query: Optional[str]) -> bool:
        if not query:
            return True
        lowered = query.casefold()
        payload = ToolPresenter.dump_item(item)
        if not isinstance(payload, dict):
            return False
        name = str(payload.get("name") or "")
        project_id = str(payload.get("id") or "")
        if self.provider.is_default_project_alias(query) and (
            self.provider.is_default_project_alias(name)
            or self.provider.is_default_project_alias(project_id)
            or name.casefold() == "inbox"
        ):
            return True
        name = name.casefold()
        project_id = project_id.casefold()
        return lowered in name or lowered in project_id

    @staticmethod
    def candidate_sort_key(item: dict[str, Any]) -> tuple[Any, Any, Any]:
        return (
            item.get("due_date_display_date") or "9999-12-31",
            item.get("due_date_display_time") is None,
            item.get("due_date_display_time") or "",
        )

    @staticmethod
    def candidate_summary(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": item.get("title"),
            "project_name": item.get("project_name"),
            "due_date_human": item.get("due_date_human"),
        }

    def update_task_by_search(
        self,
        *,
        fields: dict[str, Any],
        search: str,
        prefer_due_date: Optional[str] = None,
        prefer_today: bool = False,
        exact_title: bool = False,
        search_project_id: Optional[str] = None,
    ) -> Any:
        tasks = self.provider.list_tasks(
            status="normal",
            search=search,
            project_id=search_project_id,
        )
        payloads = [self.presenter.present(task) for task in tasks]
        normalized_search = search.strip().casefold()
        if exact_title:
            exact_matches = [
                item
                for item in payloads
                if str(item.get("title") or "").strip().casefold() == normalized_search
            ]
            if exact_matches:
                payloads = exact_matches
        if not payloads:
            return {
                "not_found": True,
                "message": f"Не нашёл открытую задачу по запросу «{search}».",
                "search": search,
            }
        if len(payloads) == 1:
            return self.provider.update_task(str(payloads[0]["id"]), fields)

        today = self.presenter._now().date().isoformat()
        candidates = payloads
        if prefer_today:
            today_matches = [
                item for item in candidates if item.get("due_date_display_date") == today
            ]
            if len(today_matches) == 1:
                return self.provider.update_task(str(today_matches[0]["id"]), fields)
            if today_matches:
                candidates = today_matches
        if prefer_due_date:
            preferred_matches = [
                item for item in candidates if item.get("due_date_display_date") == prefer_due_date
            ]
            if len(preferred_matches) == 1:
                return self.provider.update_task(str(preferred_matches[0]["id"]), fields)
            if preferred_matches:
                candidates = preferred_matches
        upcoming = sorted(candidates, key=self.candidate_sort_key)
        if (
            upcoming
            and len(upcoming) >= 2
            and self.candidate_sort_key(upcoming[0]) != self.candidate_sort_key(upcoming[1])
        ):
            return self.provider.update_task(str(upcoming[0]["id"]), fields)
        return {
            "needs_clarification": True,
            "message": f"Нашёл несколько подходящих задач по запросу «{search}». Уточни, какую именно обновить.",
            "candidates": [self.candidate_summary(item) for item in upcoming[:5]],
        }

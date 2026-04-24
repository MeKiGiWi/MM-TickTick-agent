from __future__ import annotations

import json
from datetime import date, datetime, timedelta, tzinfo
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.models import ClarifyAssessment
from app.providers.ticktick.base import TickTickProvider
from app.tools.base import ToolSpec
from app.utils.timezone import resolve_timezone


class ToolRegistry:
    MONTHS_RU = {
        1: "января",
        2: "февраля",
        3: "марта",
        4: "апреля",
        5: "мая",
        6: "июня",
        7: "июля",
        8: "августа",
        9: "сентября",
        10: "октября",
        11: "ноября",
        12: "декабря",
    }

    def __init__(
        self,
        provider: TickTickProvider,
        user_timezone: Optional[str] = None,
        now_provider: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.provider = provider
        self.user_timezone = user_timezone
        self.now_provider = now_provider
        self._tools: dict[str, ToolSpec] = {}
        self._register_defaults()

    def _register(self, tool: ToolSpec) -> None:
        self._tools[tool.name] = tool

    def _local_timezone(self) -> ZoneInfo | tzinfo:
        return resolve_timezone(self.user_timezone)

    def _now(self) -> datetime:
        timezone = self._local_timezone()
        current = self.now_provider() if self.now_provider else datetime.now(timezone)
        if current.tzinfo is None:
            return current.replace(tzinfo=timezone)
        return current.astimezone(timezone)

    @staticmethod
    def _task_timezone(payload: dict[str, Any], fallback: ZoneInfo | tzinfo) -> ZoneInfo | tzinfo:
        timezone_name = payload.get("time_zone")
        if isinstance(timezone_name, str) and timezone_name.strip():
            try:
                return ZoneInfo(timezone_name.strip())
            except ZoneInfoNotFoundError:
                return fallback
        return fallback

    @classmethod
    def _parse_ticktick_datetime(cls, value: str) -> datetime | None:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    @classmethod
    def _format_russian_date(cls, value: date, include_year: bool) -> str:
        result = f"{value.day} {cls.MONTHS_RU[value.month]}"
        if include_year:
            result = f"{result} {value.year}"
        return result

    @classmethod
    def _relative_label(cls, target_date: date, current_date: date) -> Optional[str]:
        delta_days = (target_date - current_date).days
        if delta_days < 0:
            return "просрочено"
        if delta_days == 0:
            return "сегодня"
        if delta_days == 1:
            return "завтра"
        if delta_days == 2:
            return "послезавтра"
        current_week_start = current_date - timedelta(days=current_date.weekday())
        next_week_start = current_week_start + timedelta(days=7)
        next_week_end = next_week_start + timedelta(days=6)
        if next_week_start <= target_date <= next_week_end:
            return "на следующей неделе"
        return None

    @classmethod
    def _humanize_localized_datetime(
        cls,
        localized: datetime,
        *,
        is_all_day: bool,
        current_date: date,
    ) -> tuple[str, Optional[str]]:
        target_date = localized.date()
        relative = cls._relative_label(target_date, current_date)
        include_year = target_date.year != current_date.year
        date_part = cls._format_russian_date(target_date, include_year)
        if relative == "просрочено":
            human = f"{date_part}, просрочено"
        elif relative:
            human = f"{relative}, {date_part}"
        else:
            human = date_part
        if not is_all_day:
            human = f"{human}, {localized.strftime('%H:%M')}"
        return human, relative

    def _augment_task_payload(self, payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload
        fallback_timezone = self._local_timezone()
        task_timezone = self._task_timezone(payload, fallback_timezone)
        is_all_day = bool(payload.get("is_all_day"))
        current_date = self._now().astimezone(task_timezone).date()

        def augment(prefix: str) -> None:
            raw_value = payload.get(prefix)
            if not isinstance(raw_value, str) or not raw_value:
                return
            parsed = self._parse_ticktick_datetime(raw_value)
            if parsed is None:
                return
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=task_timezone)
            localized = parsed.astimezone(task_timezone)
            payload[f"{prefix}_display"] = (
                localized.date().isoformat() if is_all_day else localized.isoformat()
            )
            payload[f"{prefix}_display_date"] = localized.date().isoformat()
            payload[f"{prefix}_display_time"] = None if is_all_day else localized.strftime("%H:%M")
            human, relative = self._humanize_localized_datetime(
                localized,
                is_all_day=is_all_day,
                current_date=current_date,
            )
            payload[f"{prefix}_human"] = human
            payload[f"{prefix}_relative"] = relative
            if prefix == "due_date":
                payload["due_date_local"] = localized.isoformat()
                payload["due_date_local_date"] = localized.date().isoformat()
                payload["due_date_local_time"] = None if is_all_day else localized.strftime("%H:%M")

        augment("due_date")
        augment("start_date")
        return payload

    @staticmethod
    def _tool_error(name: str, exc: Exception) -> dict[str, Any]:
        return {
            "error": {
                "tool": name,
                "message": str(exc),
            }
        }

    @staticmethod
    def _dump_item(item: Any) -> Any:
        if hasattr(item, "model_dump"):
            payload = item.model_dump()
            return payload
        return item

    def _wrap_handler(self, name: str, handler: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(**kwargs: Any) -> Any:
            try:
                result = handler(**kwargs)
            except Exception as exc:
                return self._tool_error(name, exc)
            if isinstance(result, list):
                return [self._augment_task_payload(self._dump_item(item)) for item in result]
            return self._augment_task_payload(self._dump_item(result))

        return wrapped

    def _project_matches_query(self, item: Any, query: Optional[str]) -> bool:
        if not query:
            return True
        lowered = query.lower()
        payload = self._dump_item(item)
        if not isinstance(payload, dict):
            return False
        name = str(payload.get("name") or "").lower()
        project_id = str(payload.get("id") or "").lower()
        return lowered in name or lowered in project_id

    def _list_projects(self, query: Optional[str] = None, **_: Any) -> list[Any]:
        projects = self.provider.list_projects()
        return [project for project in projects if self._project_matches_query(project, query)]

    def _list_upcoming_tasks(
        self,
        days: int = 30,
        limit: int = 10,
        include_overdue: bool = False,
        include_without_due_date: bool = False,
        project_id: Optional[str] = None,
        **_: Any,
    ) -> list[dict[str, Any]]:
        tasks = self.provider.list_tasks(status="normal", project_id=project_id)
        today = self._now().date()
        cutoff = today + timedelta(days=max(days, 0))
        dated: list[dict[str, Any]] = []
        undated: list[dict[str, Any]] = []
        for task in tasks:
            payload = self._augment_task_payload(self._dump_item(task))
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

    def _register_defaults(self) -> None:
        self._register(
            ToolSpec(
                name="create_task",
                description=(
                    "Create a TickTick task when the user explicitly asks to add one. "
                    "When project_id is omitted, create the task in configured inbox/default project. "
                    "Do not ask the user for project unless they explicitly require a specific project."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "project_id": {"type": "string"},
                        "content": {"type": "string"},
                        "due_date": {"type": "string"},
                        "start_date": {"type": "string"},
                        "is_all_day": {"type": "boolean"},
                        "time_zone": {"type": "string"},
                        "priority": {"type": "integer"},
                    },
                    "required": ["title"],
                },
                handler=self._wrap_handler(
                    "create_task",
                    lambda title, project_id=None, content=None, due_date=None, start_date=None, is_all_day=None, time_zone=None, priority=None, **_: self.provider.create_task(
                        title=title,
                        project_id=project_id,
                        content=content,
                        due_date=due_date,
                        start_date=start_date,
                        is_all_day=is_all_day,
                        time_zone=time_zone,
                        priority=priority,
                    ),
                ),
            )
        )
        self._register(
            ToolSpec(
                name="list_tasks",
                description=(
                    "List tasks by optional status, project, or search query. "
                    "Use this for real task lookup, including search by title/content."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "project_id": {"type": "string"},
                        "search": {"type": "string"},
                    },
                },
                handler=self._wrap_handler(
                    "list_tasks",
                    lambda **kwargs: self.provider.list_tasks(**kwargs),
                ),
            )
        )
        self._register(
            ToolSpec(
                name="get_task_details",
                description="Get full details for one task by task_id.",
                parameters={
                    "type": "object",
                    "properties": {"task_id": {"type": "string"}},
                    "required": ["task_id"],
                },
                handler=self._wrap_handler(
                    "get_task_details",
                    lambda task_id, **_: self.provider.get_task_details(task_id),
                ),
            )
        )
        self._register(
            ToolSpec(
                name="create_subtasks",
                description="Create subtasks under an existing task after the user agrees.",
                parameters={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "titles": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["task_id", "titles"],
                },
                handler=self._wrap_handler(
                    "create_subtasks",
                    lambda task_id, titles, **_: self.provider.create_subtasks(
                        task_id=task_id,
                        titles=titles,
                    ),
                ),
            )
        )
        self._register(
            ToolSpec(
                name="update_task",
                description="Update editable task fields like title, due date, priority, status, or content.",
                parameters={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "fields": {"type": "object"},
                    },
                    "required": ["task_id", "fields"],
                },
                handler=self._wrap_handler(
                    "update_task",
                    lambda task_id, fields, **_: self.provider.update_task(
                        task_id=task_id,
                        fields=fields,
                    ),
                ),
            )
        )
        self._register(
            ToolSpec(
                name="update_task_by_search",
                description=(
                    "Find an open task by title/content search and update it. "
                    "Use when user refers to a task by name instead of task_id."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "search": {"type": "string"},
                        "fields": {"type": "object"},
                        "project_id": {"type": "string"},
                        "prefer_due_date": {"type": "string"},
                        "prefer_today": {"type": "boolean"},
                        "exact_title": {"type": "boolean", "default": False},
                    },
                    "required": ["search", "fields"],
                },
                handler=self._wrap_handler(
                    "update_task_by_search",
                    self._update_task_by_search,
                ),
            )
        )
        self._register(
            ToolSpec(
                name="list_projects",
                description=(
                    "List available TickTick projects. Include the configured inbox/default project context when possible."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Optional case-insensitive filter by project name. Usually omit this.",
                        }
                    },
                    "additionalProperties": True,
                },
                handler=self._wrap_handler(
                    "list_projects",
                    self._list_projects,
                ),
            )
        )
        self._register(
            ToolSpec(
                name="list_upcoming_tasks",
                description=(
                    "List upcoming open tasks sorted by local due date. "
                    "Use for ближайшие задачи, что скоро, на неделю, дедлайны."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "default": 30},
                        "limit": {"type": "integer", "default": 10},
                        "include_overdue": {"type": "boolean", "default": False},
                        "include_without_due_date": {"type": "boolean", "default": False},
                        "project_id": {"type": "string"},
                    },
                },
                handler=self._wrap_handler(
                    "list_upcoming_tasks",
                    self._list_upcoming_tasks,
                ),
            )
        )
        self._register(
            ToolSpec(
                name="move_task",
                description="Move a task to another project.",
                parameters={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "project_id": {"type": "string"},
                    },
                    "required": ["task_id", "project_id"],
                },
                handler=self._wrap_handler(
                    "move_task",
                    lambda task_id, project_id, **_: self.provider.move_task(
                        task_id=task_id,
                        project_id=project_id,
                    ),
                ),
            )
        )
        self._register(
            ToolSpec(
                name="mark_complete",
                description="Mark a task as completed using TickTick completion flow.",
                parameters={
                    "type": "object",
                    "properties": {"task_id": {"type": "string"}},
                    "required": ["task_id"],
                },
                handler=self._wrap_handler(
                    "mark_complete",
                    lambda task_id, **_: self.provider.mark_complete(task_id),
                ),
            )
        )

    def _candidate_sort_key(self, item: dict[str, Any]) -> tuple[Any, Any, Any]:
        return (
            item.get("due_date_display_date") or "9999-12-31",
            item.get("due_date_display_time") is None,
            item.get("due_date_display_time") or "",
        )

    def _candidate_summary(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": item.get("title"),
            "project_name": item.get("project_name"),
            "due_date_human": item.get("due_date_human"),
        }

    def _update_task_by_search(
        self,
        search: str,
        fields: dict[str, object],
        project_id: Optional[str] = None,
        prefer_due_date: Optional[str] = None,
        prefer_today: bool = False,
        exact_title: bool = False,
        **_: Any,
    ) -> Any:
        tasks = self.provider.list_tasks(status="normal", search=search, project_id=project_id)
        payloads = [self._augment_task_payload(self._dump_item(task)) for task in tasks]
        normalized_search = search.strip().lower()
        if exact_title:
            exact_matches = [
                item
                for item in payloads
                if str(item.get("title") or "").strip().lower() == normalized_search
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

        today = self._now().date().isoformat()
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
        upcoming = sorted(candidates, key=self._candidate_sort_key)
        if upcoming and len(upcoming) >= 2 and self._candidate_sort_key(upcoming[0]) != self._candidate_sort_key(upcoming[1]):
            return self.provider.update_task(str(upcoming[0]["id"]), fields)
        return {
            "needs_clarification": True,
            "message": f"Нашёл несколько подходящих задач по запросу «{search}». Уточни, какую именно обновить.",
            "candidates": [self._candidate_summary(item) for item in upcoming[:5]],
        }

    def list_openrouter_tools(self) -> list[dict[str, Any]]:
        return [tool.to_openrouter_tool() for tool in self._tools.values()]

    def execute_tool(self, name: str, arguments_json: str) -> str:
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        arguments = json.loads(arguments_json or "{}")
        result = self._tools[name].handler(**arguments)
        return json.dumps(result, ensure_ascii=False)

    @staticmethod
    def clarify_assessment_to_json(assessments: list[ClarifyAssessment]) -> str:
        return json.dumps([item.model_dump() for item in assessments], ensure_ascii=False)

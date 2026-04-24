from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx

from app.domain.models import Project, Task, TickTickCredentials
from app.providers.ticktick.base import TickTickProvider
from app.utils.timezone import configured_timezone_name, resolve_timezone, timezone_label


class TickTickApiProvider(TickTickProvider):
    DEFAULT_PROJECT_ALIASES = {"inbox", "default", "входящие"}

    def __init__(
        self,
        credentials: TickTickCredentials,
        user_timezone: Optional[str] = None,
    ) -> None:
        self.credentials = credentials
        self.user_timezone = user_timezone
        self.base_url = "https://api.ticktick.com/open/v1"
        self.client = self._build_client()
        self._task_project_cache: dict[str, str] = {}
        self._projects_cache: dict[str, Project] = {}

    def _build_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.credentials.access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    @staticmethod
    def _format_request_error(exc: httpx.RequestError, method: str, path: str) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        lowered = message.lower()
        if "name or service not known" in lowered or "nodename nor servname provided" in lowered:
            detail = "ошибка DNS-разрешения имени"
        elif "temporary failure in name resolution" in lowered:
            detail = "временная ошибка DNS-разрешения имени"
        elif "timed out" in lowered or isinstance(exc, httpx.TimeoutException):
            detail = "таймаут соединения"
        else:
            detail = message
        return f"TickTick network error during {method} {path}: {detail}"

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        last_error: httpx.RequestError | None = None
        for attempt in range(3):
            try:
                response = self.client.request(method, path, **kwargs)
                break
            except httpx.RequestError as exc:
                last_error = exc
                if attempt == 0:
                    self.client.close()
                    self.client = self._build_client()
                if attempt == 2:
                    raise ValueError(self._format_request_error(exc, method, path)) from exc
        else:
            if last_error is not None:
                raise ValueError(
                    self._format_request_error(last_error, method, path)
                ) from last_error
            raise ValueError(f"TickTick network error during {method} {path}")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = response.text.strip()
            body_suffix = f": {body}" if body else ""
            raise ValueError(
                f"TickTick API error {response.status_code} {method} {path}{body_suffix}"
            ) from exc
        if not response.content:
            return {}
        return response.json()

    def _default_timezone_name(self) -> str:
        configured = configured_timezone_name(self.user_timezone)
        if configured:
            return configured
        timezone = resolve_timezone(self.user_timezone)
        return timezone_label(timezone)

    @staticmethod
    def _format_ticktick_datetime(value: datetime) -> str:
        return value.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S%z")

    @classmethod
    def _local_date_to_ticktick_all_day_datetime(cls, local_date: date, timezone_name: str) -> str:
        timezone = ZoneInfo(timezone_name)
        local_dt = datetime.combine(local_date, time.min, tzinfo=timezone)
        return cls._format_ticktick_datetime(local_dt)

    @classmethod
    def _normalize_ticktick_datetime_input(
        cls,
        value: str,
        timezone_name: str,
        is_all_day: bool,
    ) -> str:
        normalized = value.strip()
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
            try:
                parsed = datetime.strptime(normalized, fmt)
                return parsed.strftime("%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                continue
        try:
            local_date = datetime.strptime(normalized, "%Y-%m-%d").date()
        except ValueError:
            return normalized
        timezone = ZoneInfo(timezone_name)
        if is_all_day:
            return cls._local_date_to_ticktick_all_day_datetime(local_date, timezone_name)
        local_dt = datetime.combine(local_date, time.min, tzinfo=timezone)
        return cls._format_ticktick_datetime(local_dt)

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

    def _project_name_for(self, project_id: str) -> Optional[str]:
        project = self._projects_cache.get(project_id)
        if project is not None:
            return project.name
        try:
            project = self._get_project_by_id(project_id)
        except Exception:
            return None
        return project.name

    def _attach_project_name(self, task: Task) -> Task:
        task.project_name = self._project_name_for(task.project_id)
        return task

    def _normalize_task(self, payload: dict[str, Any]) -> Task:
        task = Task.model_validate(payload)
        return self._remember_task(self._attach_project_name(task))

    @staticmethod
    def _parse_project(item: Any) -> Optional[Project]:
        if not isinstance(item, dict):
            return None
        try:
            return Project.model_validate(item)
        except Exception:
            return None

    def _load_projects(self) -> list[Project]:
        payload = self._request("GET", "/project")
        items = payload if isinstance(payload, list) else []
        projects = [project for item in items if (project := self._parse_project(item)) is not None]
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

    def is_default_project_alias(self, value: str) -> bool:
        return value.strip().lower() in self.DEFAULT_PROJECT_ALIASES

    def resolve_default_project_id(self) -> str:
        configured = (self.credentials.inbox_project_id or "").strip()
        if configured:
            try:
                if not self.is_default_project_alias(configured):
                    return self._validated_project_id(configured)
            except ValueError:
                pass

        projects = self._load_projects()
        if configured:
            lowered = configured.lower()
            for project in projects:
                if project.id.lower() == lowered or project.name.lower() == lowered:
                    return project.id
        for alias in self.DEFAULT_PROJECT_ALIASES:
            for project in projects:
                if project.name.lower() == alias:
                    return project.id
        for project in projects:
            if project.kind == "TASK":
                return project.id
        if projects:
            return projects[0].id
        raise ValueError(
            "Не удалось определить project_id для новой задачи: не найден доступный inbox/default project."
        )

    def resolve_project_id(self, project_ref: Optional[str] = None) -> str:
        target = (project_ref or "").strip()
        if not target or self.is_default_project_alias(target):
            return self.resolve_default_project_id()
        try:
            return self._validated_project_id(target)
        except ValueError:
            pass
        projects = self._load_projects()
        lowered = target.lower()
        matches = [project for project in projects if project.name.lower() == lowered]
        if len(matches) == 1:
            return matches[0].id
        if matches:
            raise ValueError(f"Проект '{target}' неоднозначен, используйте точный project_id.")
        raise ValueError(f"Проект '{target}' не найден.")

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
            elif key == "projectId":
                normalized["projectId"] = value
            elif key == "due_date":
                normalized["dueDate"] = value
            elif key == "dueDate":
                normalized["dueDate"] = value
            elif key == "start_date":
                normalized["startDate"] = value
            elif key == "startDate":
                normalized["startDate"] = value
            elif key == "time_zone":
                normalized["timeZone"] = value
            elif key == "timeZone":
                normalized["timeZone"] = value
            elif key == "is_all_day":
                normalized["isAllDay"] = value
            elif key == "isAllDay":
                normalized["isAllDay"] = value
            elif key == "title":
                normalized["title"] = value
            elif key == "content":
                normalized["content"] = value
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

    def _normalize_task_datetime_fields(self, payload: dict[str, Any]) -> dict[str, Any]:
        timezone_name = str(payload.get("timeZone") or self._default_timezone_name())
        is_all_day = bool(payload.get("isAllDay"))
        for field_name in ("dueDate", "startDate"):
            value = payload.get(field_name)
            if isinstance(value, str) and value.strip():
                payload[field_name] = self._normalize_ticktick_datetime_input(
                    value,
                    timezone_name=timezone_name,
                    is_all_day=is_all_day,
                )
        if is_all_day and "timeZone" not in payload:
            payload["timeZone"] = timezone_name
        return payload

    def _task_to_update_payload(self, task: Task) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": task.id,
            "projectId": task.project_id,
            "title": task.title,
            "priority": task.priority,
        }
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
        resolved_project_id = self.resolve_project_id(project_id)
        payload: dict[str, Any] = {
            "title": title,
            "projectId": resolved_project_id,
        }
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
        payload = self._normalize_task_datetime_fields(payload)
        response = self._request("POST", "/task", json=payload)
        if isinstance(response, dict) and not response.get("projectId"):
            response = {**response, "projectId": resolved_project_id}
        return self._normalize_task(response)

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
            response = self._request("POST", "/task", json=payload)
            if isinstance(response, dict):
                response = {
                    **response,
                    "projectId": response.get("projectId") or parent.project_id,
                    "parentId": response.get("parentId") or parent.id,
                }
            created.append(self._normalize_task(response))
        return created

    def create_task_with_subtasks(
        self,
        *,
        title: str,
        subtask_titles: list[str],
        project_id: Optional[str] = None,
        content: Optional[str] = None,
        due_date: Optional[str] = None,
        start_date: Optional[str] = None,
        is_all_day: Optional[bool] = None,
        time_zone: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> dict[str, object]:
        task = self.create_task(
            title=title,
            project_id=project_id,
            content=content,
            due_date=due_date,
            start_date=start_date,
            is_all_day=is_all_day,
            time_zone=time_zone,
            priority=priority,
        )
        subtasks = self.create_subtasks(task.id, subtask_titles)
        return {"task": task, "subtasks": subtasks}

    def update_task(self, task_id: str, fields: dict[str, object]) -> Task:
        current = self.get_task_details(task_id)
        normalized_fields = self._normalize_update_fields(fields)
        merged_task = current.model_copy(
            update={
                "project_id": normalized_fields.get("projectId", current.project_id),
                "title": normalized_fields.get("title", current.title),
                "content": normalized_fields.get("content", current.content),
                "due_date": normalized_fields.get("dueDate", current.due_date),
                "start_date": normalized_fields.get("startDate", current.start_date),
                "is_all_day": normalized_fields.get("isAllDay", current.is_all_day),
                "time_zone": normalized_fields.get("timeZone", current.time_zone),
                "priority": normalized_fields.get("priority", current.priority),
            }
        )
        payload = self._task_to_update_payload(merged_task)
        payload = self._normalize_task_datetime_fields(payload)
        return self._normalize_task(self._request("POST", f"/task/{task_id}", json=payload))

    def list_projects(self) -> list[Project]:
        projects = self._load_projects()
        configured = (self.credentials.inbox_project_id or "").strip()
        if (
            configured
            and not self.is_default_project_alias(configured)
            and configured not in {project.id for project in projects}
        ):
            try:
                configured_project = self._get_project_by_id(configured)
                if configured_project.id not in {project.id for project in projects}:
                    projects.append(configured_project)
            except Exception:
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

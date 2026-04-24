from typing import Optional

from app.domain.models import Project, Task, TickTickCredentials
from app.providers.ticktick.api import TickTickApiClient
from app.providers.ticktick.mapper import TickTickTaskMapper
from app.providers.ticktick.project_refs import (
    is_default_project_alias as normalize_default_project_alias,
)
from app.providers.ticktick.project_refs import normalize_project_ref
from app.providers.ticktick.projects import TickTickProjectsService
from app.providers.ticktick.tasks import TickTickTasksService
from app.utils.timezone import configured_timezone_name, resolve_timezone, timezone_label


class TickTickApiProvider:
    def __init__(
        self,
        credentials: TickTickCredentials,
        user_timezone: Optional[str] = None,
    ) -> None:
        self.credentials = credentials
        self.user_timezone = user_timezone
        self.api = TickTickApiClient(credentials)
        self.projects = TickTickProjectsService(self.api, credentials)
        self.mapper = TickTickTaskMapper(self.projects.project_name_for)
        self.tasks = TickTickTasksService(
            self.api,
            self.projects,
            self.mapper,
            self._default_timezone_name,
        )
        self.client = self.api.client
        self.base_url = self.api.base_url
        self._task_project_cache = self.tasks.task_project_cache
        self._projects_cache = self.projects.projects_cache

    def _default_timezone_name(self) -> str:
        configured = configured_timezone_name(self.user_timezone)
        if configured:
            return configured
        timezone = resolve_timezone(self.user_timezone)
        return timezone_label(timezone)

    def normalize_project_ref(self, project_ref: Optional[str] = None) -> Optional[str]:
        return normalize_project_ref(project_ref)

    def is_default_project_alias(self, value: str) -> bool:
        return normalize_default_project_alias(value)

    def remember_default_project_id(self, project_id: Optional[str]) -> None:
        self.projects.remember_default_project_id(project_id)

    def resolve_default_project_id(self) -> str:
        return self.projects.resolve_default_project_id()

    def resolve_project_id(self, project_ref: Optional[str] = None) -> str:
        return self.projects.resolve_project_id(project_ref)

    def get_project_id(self, project_ref: Optional[str] = None) -> str:
        return self.resolve_project_id(project_ref)

    def list_projects(self) -> list[Project]:
        return self.projects.list_projects()

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
        return self.tasks.create_task(
            title=title,
            project_id=project_id,
            content=content,
            due_date=due_date,
            start_date=start_date,
            is_all_day=is_all_day,
            time_zone=time_zone,
            priority=priority,
        )

    def list_tasks(
        self,
        *,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[Task]:
        return self.tasks.list_tasks(status=status, project_id=project_id, search=search)

    def get_task_details(self, task_id: str) -> Task:
        return self.tasks.get_task_details(task_id)

    def create_subtasks(self, task_id: str, titles: list[str]) -> list[Task]:
        return self.tasks.create_subtasks(task_id, titles)

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
        return self.tasks.create_task_with_subtasks(
            title=title,
            subtask_titles=subtask_titles,
            project_id=project_id,
            content=content,
            due_date=due_date,
            start_date=start_date,
            is_all_day=is_all_day,
            time_zone=time_zone,
            priority=priority,
        )

    def update_task(self, task_id: str, fields: dict[str, object]) -> Task:
        return self.tasks.update_task(task_id, fields)

    def move_task(self, task_id: str, project_id: str) -> Task:
        return self.tasks.move_task(task_id, project_id)

    def mark_complete(self, task_id: str) -> Task:
        return self.tasks.mark_complete(task_id)

    @property
    def _default_project_id_cache(self) -> str | None:
        return self.projects.default_project_id_cache

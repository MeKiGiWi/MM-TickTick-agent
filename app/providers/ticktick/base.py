from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.domain.models import Project, Task


class TickTickProvider(ABC):
    @abstractmethod
    def resolve_project_id(self, project_ref: Optional[str] = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def resolve_default_project_id(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def is_default_project_alias(self, value: str) -> bool:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    def list_tasks(
        self,
        *,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[Task]:
        raise NotImplementedError

    @abstractmethod
    def get_task_details(self, task_id: str) -> Task:
        raise NotImplementedError

    @abstractmethod
    def create_subtasks(self, task_id: str, titles: list[str]) -> list[Task]:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    def update_task(self, task_id: str, fields: dict[str, object]) -> Task:
        raise NotImplementedError

    @abstractmethod
    def list_projects(self) -> list[Project]:
        raise NotImplementedError

    @abstractmethod
    def move_task(self, task_id: str, project_id: str) -> Task:
        raise NotImplementedError

    @abstractmethod
    def mark_complete(self, task_id: str) -> Task:
        raise NotImplementedError

from __future__ import annotations

from copy import deepcopy
from typing import Optional

from app.domain.models import Project, Task
from app.providers.ticktick.base import TickTickProvider


class MockTickTickProvider(TickTickProvider):
    def __init__(self) -> None:
        self.projects: dict[str, Project] = {
            "inbox": Project(id="inbox", name="Inbox"),
            "work": Project(id="work", name="Work"),
            "personal": Project(id="personal", name="Personal"),
        }
        self.tasks: dict[str, Task] = {
            "task-1": Task(
                id="task-1",
                title="Разобрать inbox по GTD",
                project_id="inbox",
                content="Слишком большая формулировка, нужен clarify",
            ),
            "task-2": Task(
                id="task-2",
                title="Подготовить квартальный отчет",
                project_id="work",
                due_date="2026-04-18",
                is_overdue=True,
            ),
            "task-3": Task(
                id="task-3",
                title="Купить лампочку",
                project_id="personal",
            ),
            "task-4": Task(
                id="task-4",
                title="Спланировать отпуск",
                project_id="personal",
                content="Нужно решить маршрут, бюджет и даты",
            ),
        }
        self.counter = 100

    def _attach_project_name(self, task: Task) -> Task:
        project = self.projects.get(task.project_id)
        task.project_name = project.name if project else None
        return task

    @staticmethod
    def is_default_project_alias(value: str) -> bool:
        return value.strip().lower() in {"", "inbox", "default", "входящие"}

    def resolve_default_project_id(self) -> str:
        return "inbox"

    def resolve_project_id(self, project_ref: Optional[str] = None) -> str:
        value = (project_ref or "").strip()
        if not value or self.is_default_project_alias(value):
            return self.resolve_default_project_id()
        if value in self.projects:
            return value
        for project in self.projects.values():
            if project.name.lower() == value.lower():
                return project.id
        raise ValueError(f"Проект '{value}' не найден.")

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
        target_project_id = self.resolve_project_id(project_id)
        self.counter += 1
        task = Task(
            id=f"task-{self.counter}",
            title=title,
            project_id=target_project_id,
            project_name=self.projects[target_project_id].name,
            content=content,
            due_date=due_date,
            start_date=start_date,
            is_all_day=bool(is_all_day),
            time_zone=time_zone,
            priority=priority or 0,
        )
        self.tasks[task.id] = task
        return deepcopy(self._attach_project_name(task))

    def list_tasks(
        self,
        *,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[Task]:
        tasks = list(self.tasks.values())
        if status:
            tasks = [task for task in tasks if task.status == status]
        if project_id:
            tasks = [task for task in tasks if task.project_id == project_id]
        if search:
            lowered = search.lower()
            tasks = [task for task in tasks if lowered in task.title.lower()]
        return [deepcopy(self._attach_project_name(task)) for task in tasks]

    def get_task_details(self, task_id: str) -> Task:
        return deepcopy(self._attach_project_name(self.tasks[task_id]))

    def create_subtasks(self, task_id: str, titles: list[str]) -> list[Task]:
        parent = self.tasks[task_id]
        created: list[Task] = []
        for title in titles:
            self.counter += 1
            subtask = Task(
                id=f"task-{self.counter}",
                title=title,
                project_id=parent.project_id,
                project_name=self.projects[parent.project_id].name,
                parent_id=parent.id,
            )
            parent.subtasks.append(subtask)
            self.tasks[subtask.id] = subtask
            created.append(deepcopy(self._attach_project_name(subtask)))
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
        task = self.tasks[task_id]
        for key, value in fields.items():
            if hasattr(task, key):
                setattr(task, key, value)
        return deepcopy(self._attach_project_name(task))

    def list_projects(self) -> list[Project]:
        return [deepcopy(project) for project in self.projects.values()]

    def move_task(self, task_id: str, project_id: str) -> Task:
        task = self.tasks[task_id]
        task.project_id = project_id
        return deepcopy(self._attach_project_name(task))

    def mark_complete(self, task_id: str) -> Task:
        task = self.tasks[task_id]
        task.status = "completed"
        return deepcopy(self._attach_project_name(task))

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

    def create_task(
        self,
        *,
        title: str,
        project_id: Optional[str] = None,
        content: Optional[str] = None,
        due_date: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> Task:
        target_project_id = project_id or "inbox"
        if target_project_id not in self.projects:
            raise ValueError(f"Проект '{target_project_id}' не найден.")
        self.counter += 1
        task = Task(
            id=f"task-{self.counter}",
            title=title,
            project_id=target_project_id,
            content=content,
            due_date=due_date,
            priority=priority or 0,
        )
        self.tasks[task.id] = task
        return deepcopy(task)

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
        return [deepcopy(task) for task in tasks]

    def get_task_details(self, task_id: str) -> Task:
        return deepcopy(self.tasks[task_id])

    def create_subtasks(self, task_id: str, titles: list[str]) -> list[Task]:
        parent = self.tasks[task_id]
        created: list[Task] = []
        for title in titles:
            self.counter += 1
            subtask = Task(id=f"task-{self.counter}", title=title, project_id=parent.project_id)
            parent.subtasks.append(subtask)
            self.tasks[subtask.id] = subtask
            created.append(deepcopy(subtask))
        return created

    def update_task(self, task_id: str, fields: dict[str, object]) -> Task:
        task = self.tasks[task_id]
        for key, value in fields.items():
            if hasattr(task, key):
                setattr(task, key, value)
        return deepcopy(task)

    def list_projects(self) -> list[Project]:
        return [deepcopy(project) for project in self.projects.values()]

    def move_task(self, task_id: str, project_id: str) -> Task:
        task = self.tasks[task_id]
        task.project_id = project_id
        return deepcopy(task)

    def mark_complete(self, task_id: str) -> Task:
        task = self.tasks[task_id]
        task.status = "completed"
        return deepcopy(task)

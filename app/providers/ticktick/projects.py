from typing import Any, Optional

from app.domain.models import Project, TickTickCredentials
from app.providers.ticktick.api import TickTickApiClient
from app.providers.ticktick.project_refs import (
    classify_project_ref,
    is_default_project_alias,
    normalize_project_ref,
)


class TickTickProjectsService:
    def __init__(self, api: TickTickApiClient, credentials: TickTickCredentials) -> None:
        self.api = api
        self.credentials = credentials
        self.projects_cache: dict[str, Project] = {}
        self.default_project_id_cache: str | None = None

    @staticmethod
    def parse_project(item: Any) -> Optional[Project]:
        if not isinstance(item, dict):
            return None
        try:
            return Project.model_validate(item)
        except Exception:
            return None

    @staticmethod
    def looks_like_default_project_id(project_id: Optional[str]) -> bool:
        normalized = (project_id or "").strip().casefold()
        return normalized.startswith("inbox")

    def remember_default_project_id(self, project_id: Optional[str]) -> None:
        if self.looks_like_default_project_id(project_id):
            resolved = str(project_id).strip()
            self.default_project_id_cache = resolved
            self.credentials.inbox_project_id = resolved

    def load_projects(self) -> list[Project]:
        payload = self.api.request("GET", "/project")
        items = payload if isinstance(payload, list) else []
        projects = [project for item in items if (project := self.parse_project(item)) is not None]
        self.projects_cache = {project.id: project for project in projects}
        for project in projects:
            if self.looks_like_default_project_id(project.id) or is_default_project_alias(
                project.name
            ):
                self.remember_default_project_id(project.id)
        return projects

    def get_project_by_id(self, project_id: str) -> Project:
        if project_id in self.projects_cache:
            return self.projects_cache[project_id]
        payload = self.api.request("GET", f"/project/{project_id}")
        if not payload and self.looks_like_default_project_id(project_id):
            project = Project(id=project_id, name="Inbox", kind="TASK")
        else:
            project = Project.model_validate(payload)
        self.projects_cache[project.id] = project
        if self.looks_like_default_project_id(project.id) or is_default_project_alias(project.name):
            self.remember_default_project_id(project.id)
        return project

    def project_name_for(self, project_id: str) -> Optional[str]:
        project = self.projects_cache.get(project_id)
        if project is not None:
            return project.name
        try:
            project = self.get_project_by_id(project_id)
        except Exception:
            return None
        return project.name

    def validated_project_id(self, project_id: str) -> str:
        self.get_project_by_id(project_id)
        return project_id

    def configured_default_project_id(self) -> Optional[str]:
        configured = normalize_project_ref(self.credentials.inbox_project_id)
        if not configured or configured == "inbox":
            return None
        try:
            resolved = self.validated_project_id(configured)
        except Exception:
            return None
        self.remember_default_project_id(resolved)
        return resolved

    def infer_default_project_id_from_projects(
        self, projects: list[Project], configured: Optional[str] = None
    ) -> Optional[str]:
        if configured:
            lowered = configured.casefold()
            for project in projects:
                if project.id.casefold() == lowered or project.name.casefold() == lowered:
                    self.remember_default_project_id(project.id)
                    return project.id
        for alias in {"inbox", "входящие", "инбокс"}:
            for project in projects:
                if project.name.casefold() == alias:
                    self.remember_default_project_id(project.id)
                    return project.id
        return None

    def infer_default_project_id_from_tasks(self) -> Optional[str]:
        try:
            payload = self.api.request("POST", "/task/filter", json={"status": [0]})
        except Exception:
            return None
        items = payload if isinstance(payload, list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            project_id = str(item.get("projectId") or item.get("project_id") or "").strip()
            project_name = str(item.get("projectName") or item.get("project_name") or "").strip()
            if self.looks_like_default_project_id(project_id) or is_default_project_alias(
                project_name
            ):
                self.remember_default_project_id(project_id)
                return project_id
        return None

    def resolve_default_project_id(self) -> str:
        if self.default_project_id_cache:
            return self.default_project_id_cache

        configured = normalize_project_ref(self.credentials.inbox_project_id)
        configured_real_id = self.configured_default_project_id()
        if configured_real_id:
            return configured_real_id

        projects = self.load_projects()
        inferred_from_projects = self.infer_default_project_id_from_projects(projects, configured)
        if inferred_from_projects:
            return inferred_from_projects
        inferred = self.infer_default_project_id_from_tasks()
        if inferred:
            self.remember_default_project_id(inferred)
            return inferred
        raise ValueError(
            "Не удалось определить real project_id для Inbox. Укажите ticktick.inbox_project_id "
            'в config.local.json, например "inbox121427197". Literal alias "inbox" подходит '
            "только для tool calls, но не для TickTick API."
        )

    def resolve_project_id(self, project_ref: Optional[str] = None) -> str:
        normalized = normalize_project_ref(project_ref)
        if normalized == "inbox":
            return self.resolve_default_project_id()
        if classify_project_ref(normalized) == "id":
            try:
                resolved = self.validated_project_id(normalized)
                self.remember_default_project_id(resolved)
                return resolved
            except ValueError:
                pass
        projects = self.load_projects()
        lowered = (normalized or "").casefold()
        matches = [project for project in projects if project.name.casefold() == lowered]
        if len(matches) == 1:
            self.remember_default_project_id(matches[0].id)
            return matches[0].id
        if matches:
            raise ValueError(f"Проект '{normalized}' неоднозначен, используйте точный project_id.")
        raise ValueError(f"Проект '{normalized}' не найден.")

    def list_projects(self) -> list[Project]:
        projects = self.load_projects()
        project_ids = {project.id for project in projects}
        try:
            inbox_project_id = self.resolve_default_project_id()
        except ValueError:
            inbox_project_id = None

        if inbox_project_id and inbox_project_id not in project_ids:
            try:
                configured_project = self.get_project_by_id(inbox_project_id)
                inbox_project = configured_project.model_copy(update={"name": "Inbox"})
            except Exception:
                inbox_project = Project(id=inbox_project_id, name="Inbox", kind="TASK")
            projects.append(inbox_project)
            project_ids.add(inbox_project.id)

        configured = normalize_project_ref(self.credentials.inbox_project_id)
        if configured and configured != "inbox" and configured not in project_ids:
            try:
                configured_project = self.get_project_by_id(configured)
                if configured_project.id not in project_ids:
                    projects.append(configured_project)
            except Exception:
                projects.append(Project(id=configured, name="Inbox (configured)", kind="TASK"))
        return projects

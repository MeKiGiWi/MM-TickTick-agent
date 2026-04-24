from app.domain.models import Project
from app.providers.ticktick.client import TickTickApiProvider


class LocalCommandHandler:
    def __init__(self, provider: TickTickApiProvider) -> None:
        self.provider = provider

    @staticmethod
    def format_projects_output(projects: list[Project]) -> str:
        if not projects:
            return "Проекты не найдены."
        lines = ["Проекты:"]
        for project in projects:
            lines.append(f"- {project.name} ({project.id})")
            if project.kind:
                lines.append(f"  kind: {project.kind}")
        return "\n".join(lines)

    def handle(self, user_input: str) -> bool:
        if user_input != "/projects":
            return False
        projects = self.provider.list_projects()
        print()
        print(self.format_projects_output(projects))
        return True

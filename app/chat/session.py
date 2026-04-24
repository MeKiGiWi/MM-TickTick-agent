from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.domain.models import Project
from app.chat.prompts import SYSTEM_PROMPT
from app.config.setup import ensure_config
from app.llm.openrouter import OpenRouterClient, OpenRouterToolLoop
from app.services.provider_factory import build_ticktick_provider
from app.tools.registry import ToolRegistry
from app.utils.timezone import resolve_timezone, timezone_label


class ChatSession:
    RUNTIME_CONTEXT_PREFIX = "Runtime context:"
    USER_PROMPT = "🙂 you> "
    AGENT_PROMPT = "🤖 agent> "

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.config = ensure_config(self.root)
        self.provider = build_ticktick_provider(
            self.config.ticktick,
            self.root,
            user_timezone=self.config.user_timezone,
        )
        self.registry = ToolRegistry(self.provider, user_timezone=self.config.user_timezone)
        self.llm = OpenRouterToolLoop(
            OpenRouterClient(self.config.openrouter),
            self.registry,
            max_tool_steps=self.config.openrouter.max_tool_steps,
        )
        self.messages: list[dict[str, object]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    @classmethod
    def _build_runtime_context_message(cls, user_timezone: Optional[str] = None) -> str:
        timezone = resolve_timezone(user_timezone)
        now = datetime.now(timezone)
        timezone_name = timezone_label(timezone)
        return (
            f"{cls.RUNTIME_CONTEXT_PREFIX} "
            f"Current local datetime is {now.isoformat()}. "
            f"Current local date is {now.date().isoformat()}. "
            f"Timezone is {timezone_name}. "
            "Use this as the source of truth for words like today, tomorrow, this week, and nearest week."
        )

    @classmethod
    def _upsert_runtime_context(
        cls,
        messages: list[dict[str, object]],
        user_timezone: Optional[str] = None,
    ) -> list[dict[str, object]]:
        filtered: list[dict[str, object]] = []
        for message in messages:
            content = message.get("content")
            if (
                message.get("role") == "system"
                and isinstance(content, str)
                and content.startswith(cls.RUNTIME_CONTEXT_PREFIX)
            ):
                continue
            filtered.append(message)
        filtered.append(
            {"role": "system", "content": cls._build_runtime_context_message(user_timezone)}
        )
        return filtered

    @staticmethod
    def _sanitize_text(value: str) -> str:
        if not any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            return value
        return value.encode("utf-8", "surrogateescape").decode("utf-8", "replace")

    @classmethod
    def _sanitize_payload(cls, value: Any) -> Any:
        if isinstance(value, str):
            return cls._sanitize_text(value)
        if isinstance(value, list):
            return [cls._sanitize_payload(item) for item in value]
        if isinstance(value, dict):
            return {key: cls._sanitize_payload(item) for key, item in value.items()}
        return value

    @staticmethod
    def _format_turn_error(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        lowered = message.lower()
        if "network error" in lowered or "dns" in lowered or "connection error" in lowered:
            return (
                f"Не удалось обработать ход из-за временной сетевой ошибки. Подробности: {message}"
            )
        return f"Не удалось обработать ход: {message}"

    @staticmethod
    def _format_projects_output(projects: list[Project]) -> str:
        if not projects:
            return "Проекты не найдены."
        lines = ["Проекты:"]
        for project in projects:
            lines.append(f"- {project.name} ({project.id})")
            if project.kind:
                lines.append(f"  kind: {project.kind}")
        return "\n".join(lines)

    def _handle_local_command(self, user_input: str) -> bool:
        if user_input != "/projects":
            return False
        projects = self.provider.list_projects()
        print()
        print(self._format_projects_output(projects))
        return True

    def run(self) -> None:
        print("TickTick chat agent запущен. Напишите сообщение. Для выхода: exit")
        while True:
            user_input = self._sanitize_text(input(self.USER_PROMPT).strip())
            if user_input.lower() in {"exit", "quit"}:
                print("bye")
                break
            if not user_input:
                continue
            if self._handle_local_command(user_input):
                continue
            self.messages.append({"role": "user", "content": user_input})
            try:
                self.messages = self._upsert_runtime_context(
                    self.messages,
                    user_timezone=self.config.user_timezone,
                )
                self.messages = self._sanitize_payload(self.messages)
                answer, updated_messages = self.llm.run_turn(self.messages)
            except Exception as exc:
                answer = self._format_turn_error(exc)
                updated_messages = self.messages + [{"role": "assistant", "content": answer}]
            self.messages = updated_messages
            answer = answer.strip()
            if not answer:
                answer = "Не получил текстовый ответ от модели."
            print()
            print(f"{self.AGENT_PROMPT}{answer}")

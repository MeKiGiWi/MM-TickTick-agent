import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.domain.models import Project
from app.chat.prompts import SYSTEM_PROMPT
from app.config.setup import ensure_config
from app.llm.openrouter import OpenRouterClient, OpenRouterToolLoop
from app.providers.ticktick.client import TickTickApiProvider
from app.storage.config_store import ConfigStore
from app.tools.registry import ToolRegistry
from app.utils.timezone import resolve_timezone, timezone_label


class ChatSession:
    RUNTIME_CONTEXT_PREFIX = "Runtime context:"
    USER_PROMPT = "🙂 you> "
    AGENT_PROMPT = "🤖 agent> "
    SYSTEM_INFO_PROMPT = "ℹ️ system> "

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.config_store = ConfigStore(self.root)
        self.config = ensure_config(self.root)
        self.provider = TickTickApiProvider(
            credentials=self.config.ticktick,
            user_timezone=self.config.user_timezone,
        )
        self.registry = ToolRegistry(self.provider, user_timezone=self.config.user_timezone)
        self.llm = OpenRouterToolLoop(
            OpenRouterClient(self.config.openrouter),
            self.registry,
            max_tool_steps=self.config.openrouter.max_tool_steps,
        )
        self.debug_tool_flow = os.getenv("DEBUG_TOOL_FLOW", "1") != "0"
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

    @staticmethod
    def _pretty_json(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except TypeError:
            return str(value)

    @classmethod
    def _extract_tool_debug_lines(
        cls,
        previous_messages: list[dict[str, object]],
        updated_messages: list[dict[str, object]],
    ) -> list[str]:
        new_messages = updated_messages[len(previous_messages) :]
        lines: list[str] = []
        for message in new_messages:
            if message.get("role") == "assistant":
                for tool_call in message.get("tool_calls", []) or []:
                    function = tool_call.get("function", {})
                    name = function.get("name", "unknown")
                    arguments = function.get("arguments", "{}")
                    try:
                        parsed_arguments = json.loads(arguments)
                    except Exception:
                        parsed_arguments = arguments
                    lines.append(f"tool call: {name}")
                    lines.append(cls._pretty_json(parsed_arguments))
            elif message.get("role") == "tool":
                lines.append(f"tool result: {message.get('name', 'unknown')}")
                content = message.get("content", "")
                try:
                    parsed_content = json.loads(content) if isinstance(content, str) else content
                except Exception:
                    parsed_content = content
                lines.append(cls._pretty_json(parsed_content))
        return lines

    def _print_tool_debug_info(
        self,
        previous_messages: list[dict[str, object]],
        updated_messages: list[dict[str, object]],
    ) -> None:
        if not getattr(self, "debug_tool_flow", True):
            return
        lines = self._extract_tool_debug_lines(previous_messages, updated_messages)
        if not lines:
            return
        print()
        print(f"{self.SYSTEM_INFO_PROMPT}tool flow")
        for line in lines:
            print(line)

    def _persist_config_if_needed(self) -> None:
        ticktick_config = getattr(self.config, "ticktick", None)
        if ticktick_config is None:
            return
        inbox_project_id = getattr(ticktick_config, "inbox_project_id", "")
        if not isinstance(inbox_project_id, str) or not inbox_project_id.casefold().startswith(
            "inbox"
        ):
            return
        config_store = getattr(self, "config_store", None)
        if config_store is None or not config_store.exists():
            return
        stored = config_store.load()
        if stored.ticktick.inbox_project_id == inbox_project_id:
            return
        config_store.save(self.config)

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
            previous_messages = list(self.messages)
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
            self._persist_config_if_needed()
            answer = answer.strip()
            if not answer:
                answer = "Не получил текстовый ответ от модели."
            self._print_tool_debug_info(previous_messages, updated_messages)
            print()
            print(f"{self.AGENT_PROMPT}{answer}")

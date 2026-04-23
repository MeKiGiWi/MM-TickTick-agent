from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.agents.clarify import ClarifyAgent
from app.chat.prompts import SYSTEM_PROMPT
from app.config.setup import ensure_config
from app.llm.openrouter import OpenRouterClient, OpenRouterToolLoop
from app.services.provider_factory import build_ticktick_provider
from app.tools.registry import ToolRegistry


class ChatSession:
    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2]
        self.config = ensure_config(self.root)
        self.provider = build_ticktick_provider(self.config.ticktick, self.root)
        self.registry = ToolRegistry(self.provider)
        self.llm = OpenRouterToolLoop(OpenRouterClient(self.config.openrouter), self.registry)
        self.clarify_agent = ClarifyAgent()
        self.messages: list[dict[str, object]] = [{"role": "system", "content": SYSTEM_PROMPT}]

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

    def run(self) -> None:
        print("TickTick chat agent запущен. Напишите сообщение. Для выхода: exit")
        while True:
            user_input = self._sanitize_text(input("you> ").strip())
            if user_input.lower() in {"exit", "quit"}:
                print("bye")
                break
            if not user_input:
                continue
            self.messages.append({"role": "user", "content": user_input})
            self._maybe_add_clarify_context(user_input)
            try:
                self.messages = self._sanitize_payload(self.messages)
                answer, updated_messages = self.llm.run_turn(self.messages)
            except Exception as exc:
                answer = f"Не удалось обработать ход: {exc}"
                updated_messages = self.messages + [{"role": "assistant", "content": answer}]
            self.messages = updated_messages
            print(f"agent> {answer}")

    def _maybe_add_clarify_context(self, user_input: str) -> None:
        lowered = user_input.lower()
        if "подзадач" not in lowered and "разбей" not in lowered and "clarify" not in lowered:
            return
        tasks = self.provider.list_tasks()
        assessments = self.clarify_agent.assess_tasks(tasks)
        formatted = self.registry.clarify_assessment_to_json(assessments)
        self.messages.append(
            {
                "role": "system",
                "content": (
                    "Ниже локальная эвристическая оценка Clarify Agent по текущим задачам. "
                    f"Используй ее как вспомогательный контекст: {formatted}"
                ),
            }
        )

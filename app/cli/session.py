import os
from pathlib import Path
from typing import Optional

from app.chat.prompts import SYSTEM_PROMPT
from app.cli.commands import LocalCommandHandler
from app.cli.context import RuntimeContextBuilder
from app.cli.debug import ToolDebugPrinter
from app.config.setup import ensure_config
from app.llm.openrouter import OpenRouterClient, OpenRouterToolLoop
from app.providers.ticktick.client import TickTickApiProvider
from app.storage.config_store import ConfigStore
from app.tools.registry import ToolRegistry


class ChatSession:
    USER_PROMPT = "🙂 you> "
    AGENT_PROMPT = "🤖 agent> "

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
        self.commands = LocalCommandHandler(self.provider)
        self.debug_tool_flow = os.getenv("DEBUG_TOOL_FLOW", "1") != "0"
        self.messages: list[dict[str, object]] = [{"role": "system", "content": SYSTEM_PROMPT}]

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
            user_input = RuntimeContextBuilder.sanitize_text(input(self.USER_PROMPT).strip())
            if user_input.lower() in {"exit", "quit"}:
                print("bye")
                break
            if not user_input:
                continue
            if self.commands.handle(user_input):
                continue
            self.messages.append({"role": "user", "content": user_input})
            previous_messages = list(self.messages)
            try:
                self.messages = RuntimeContextBuilder.upsert(
                    self.messages,
                    user_timezone=self.config.user_timezone,
                )
                self.messages = RuntimeContextBuilder.sanitize_payload(self.messages)
                answer, updated_messages = self.llm.run_turn(self.messages)
            except Exception as exc:
                answer = RuntimeContextBuilder.format_turn_error(exc)
                updated_messages = self.messages + [{"role": "assistant", "content": answer}]
            self.messages = updated_messages
            self._persist_config_if_needed()
            answer = answer.strip() or "Не получил текстовый ответ от модели."
            ToolDebugPrinter.print_if_enabled(
                self.debug_tool_flow,
                previous_messages,
                updated_messages,
            )
            print()
            print(f"{self.AGENT_PROMPT}{answer}")

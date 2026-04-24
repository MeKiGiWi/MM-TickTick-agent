import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from app.providers.ticktick.client import TickTickApiProvider
from app.tools.base import ToolSpec
from app.tools.handlers import ToolHandlers
from app.tools.presenter import ToolPresenter
from app.tools.task_search import TaskSearch


class ToolRegistry:
    def __init__(
        self,
        provider: TickTickApiProvider,
        user_timezone: Optional[str] = None,
        now_provider: Optional[Callable[[], datetime]] = None,
        specs_path: Optional[Path] = None,
    ) -> None:
        self.provider = provider
        self.user_timezone = user_timezone
        self.now_provider = now_provider
        self.specs_path = specs_path or Path(__file__).with_name("specs") / "ticktick_tools.json"
        self._tools: dict[str, ToolSpec] = {}
        self.presenter = ToolPresenter(
            user_timezone=self.user_timezone,
            now_provider=self.now_provider,
        )
        self.task_search = TaskSearch(provider, self.presenter)
        self.handlers = ToolHandlers(provider, self.presenter, self.task_search)
        self._register_defaults()

    def _register(self, tool: ToolSpec) -> None:
        self._tools[tool.name] = tool

    def _load_tool_specs(self) -> list[dict[str, Any]]:
        payload = json.loads(self.specs_path.read_text(encoding="utf-8"))
        tools = payload.get("tools")
        if not isinstance(tools, list):
            raise ValueError(f"Invalid tool specs format in {self.specs_path}")
        return tools

    @classmethod
    def _parse_ticktick_datetime(cls, value: str):
        return ToolPresenter.parse_ticktick_datetime(value)

    def _augment_task_payload(self, payload: Any) -> Any:
        return self.presenter.augment_task_payload(payload)

    def _wrap_handler(self, name: str, handler: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(**kwargs: Any) -> Any:
            try:
                result = handler(**kwargs)
            except Exception as exc:
                return self.presenter.tool_error(name, exc)
            return self.presenter.present(result)

        return wrapped

    def _register_defaults(self) -> None:
        handlers: dict[str, Callable[..., Any]] = {
            "create_task": self.handlers.create_task,
            "create_task_with_subtasks": self.handlers.create_task_with_subtasks,
            "list_tasks": self.handlers.list_tasks,
            "get_task_details": self.handlers.get_task_details,
            "create_subtasks": self.handlers.create_subtasks,
            "update_task": self.handlers.update_task,
            "update_task_by_search": self.handlers.update_task_by_search,
            "list_projects": self.handlers.list_projects,
            "list_upcoming_tasks": self.handlers.list_upcoming_tasks,
            "move_task": self.handlers.move_task,
            "mark_complete": self.handlers.mark_complete,
        }
        for spec in self._load_tool_specs():
            name = spec["name"]
            handler = handlers.get(name)
            if handler is None:
                raise ValueError(f"No handler registered for tool: {name}")
            self._register(
                ToolSpec(
                    name=name,
                    description=spec["description"],
                    parameters=spec["parameters"],
                    handler=self._wrap_handler(name, handler),
                )
            )

    def list_openrouter_tools(self) -> list[dict[str, Any]]:
        return [tool.to_openrouter_tool() for tool in self._tools.values()]

    def execute_tool(self, name: str, arguments_json: str) -> str:
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")
        arguments = json.loads(arguments_json or "{}")
        result = self._tools[name].handler(**arguments)
        return json.dumps(result, ensure_ascii=False)

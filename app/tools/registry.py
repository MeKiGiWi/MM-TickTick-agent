from __future__ import annotations

import json
from typing import Any, Callable

from app.domain.models import ClarifyAssessment
from app.providers.ticktick.base import TickTickProvider
from app.tools.base import ToolSpec


class ToolRegistry:
    def __init__(self, provider: TickTickProvider) -> None:
        self.provider = provider
        self._tools: dict[str, ToolSpec] = {}
        self._register_defaults()

    def _register(self, tool: ToolSpec) -> None:
        self._tools[tool.name] = tool

    @staticmethod
    def _tool_error(name: str, exc: Exception) -> dict[str, Any]:
        return {
            "error": {
                "tool": name,
                "message": str(exc),
            }
        }

    @staticmethod
    def _dump_item(item: Any) -> Any:
        if hasattr(item, "model_dump"):
            return item.model_dump()
        return item

    def _wrap_handler(self, name: str, handler: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(**kwargs: Any) -> Any:
            try:
                result = handler(**kwargs)
            except Exception as exc:
                return self._tool_error(name, exc)
            if isinstance(result, list):
                return [self._dump_item(item) for item in result]
            return self._dump_item(result)

        return wrapped

    def _register_defaults(self) -> None:
        self._register(
            ToolSpec(
                name="create_task",
                description=(
                    "Create a TickTick task when the user explicitly asks to add one. "
                    "If project_id is omitted, use the configured inbox/default project."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "project_id": {"type": "string"},
                        "content": {"type": "string"},
                        "due_date": {"type": "string"},
                        "priority": {"type": "integer"},
                    },
                    "required": ["title"],
                },
                handler=self._wrap_handler(
                    "create_task",
                    lambda title, project_id=None, content=None, due_date=None, priority=None, **_: self.provider.create_task(
                        title=title,
                        project_id=project_id,
                        content=content,
                        due_date=due_date,
                        priority=priority,
                    ),
                ),
            )
        )
        self._register(
            ToolSpec(
                name="list_tasks",
                description=(
                    "List tasks by optional status, project, or search query. "
                    "Use this for real task lookup, including search by title/content."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "project_id": {"type": "string"},
                        "search": {"type": "string"},
                    },
                },
                handler=self._wrap_handler(
                    "list_tasks",
                    lambda **kwargs: self.provider.list_tasks(**kwargs),
                ),
            )
        )
        self._register(
            ToolSpec(
                name="get_task_details",
                description="Get full details for one task by task_id.",
                parameters={
                    "type": "object",
                    "properties": {"task_id": {"type": "string"}},
                    "required": ["task_id"],
                },
                handler=self._wrap_handler(
                    "get_task_details",
                    lambda task_id, **_: self.provider.get_task_details(task_id),
                ),
            )
        )
        self._register(
            ToolSpec(
                name="create_subtasks",
                description="Create subtasks under an existing task after the user agrees.",
                parameters={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "titles": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["task_id", "titles"],
                },
                handler=self._wrap_handler(
                    "create_subtasks",
                    lambda task_id, titles, **_: self.provider.create_subtasks(
                        task_id=task_id,
                        titles=titles,
                    ),
                ),
            )
        )
        self._register(
            ToolSpec(
                name="update_task",
                description="Update editable task fields like title, due date, priority, status, or content.",
                parameters={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "fields": {"type": "object"},
                    },
                    "required": ["task_id", "fields"],
                },
                handler=self._wrap_handler(
                    "update_task",
                    lambda task_id, fields, **_: self.provider.update_task(
                        task_id=task_id,
                        fields=fields,
                    ),
                ),
            )
        )
        self._register(
            ToolSpec(
                name="list_projects",
                description=(
                    "List available TickTick projects. Include the configured inbox/default project context when possible."
                ),
                parameters={"type": "object", "properties": {}},
                handler=self._wrap_handler(
                    "list_projects",
                    lambda **_: self.provider.list_projects(),
                ),
            )
        )
        self._register(
            ToolSpec(
                name="move_task",
                description="Move a task to another project.",
                parameters={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "project_id": {"type": "string"},
                    },
                    "required": ["task_id", "project_id"],
                },
                handler=self._wrap_handler(
                    "move_task",
                    lambda task_id, project_id, **_: self.provider.move_task(
                        task_id=task_id,
                        project_id=project_id,
                    ),
                ),
            )
        )
        self._register(
            ToolSpec(
                name="mark_complete",
                description="Mark a task as completed using TickTick completion flow.",
                parameters={
                    "type": "object",
                    "properties": {"task_id": {"type": "string"}},
                    "required": ["task_id"],
                },
                handler=self._wrap_handler(
                    "mark_complete",
                    lambda task_id, **_: self.provider.mark_complete(task_id),
                ),
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

    @staticmethod
    def clarify_assessment_to_json(assessments: list[ClarifyAssessment]) -> str:
        return json.dumps([item.model_dump() for item in assessments], ensure_ascii=False)

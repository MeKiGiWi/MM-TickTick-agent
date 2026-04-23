from __future__ import annotations

import json
from typing import Any

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

    def _register_defaults(self) -> None:
        self._register(
            ToolSpec(
                name="list_tasks",
                description="List tasks by optional status, project, or search query.",
                parameters={
                    "type": "object",
                    "properties": {
                        "status": {"type": "string"},
                        "project_id": {"type": "string"},
                        "search": {"type": "string"},
                    },
                },
                handler=lambda **kwargs: [
                    task.model_dump() for task in self.provider.list_tasks(**kwargs)
                ],
            )
        )
        self._register(
            ToolSpec(
                name="get_task_details",
                description="Get full details for one task.",
                parameters={
                    "type": "object",
                    "properties": {"task_id": {"type": "string"}},
                    "required": ["task_id"],
                },
                handler=lambda task_id, **_: self.provider.get_task_details(task_id).model_dump(),
            )
        )
        self._register(
            ToolSpec(
                name="create_subtasks",
                description="Create subtasks under an existing task.",
                parameters={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "titles": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["task_id", "titles"],
                },
                handler=lambda task_id, titles, **_: [
                    task.model_dump()
                    for task in self.provider.create_subtasks(task_id=task_id, titles=titles)
                ],
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
                handler=lambda task_id, fields, **_: self.provider.update_task(
                    task_id=task_id,
                    fields=fields,
                ).model_dump(),
            )
        )
        self._register(
            ToolSpec(
                name="list_projects",
                description="List available TickTick projects.",
                parameters={"type": "object", "properties": {}},
                handler=lambda **_: [
                    project.model_dump() for project in self.provider.list_projects()
                ],
            )
        )
        self._register(
            ToolSpec(
                name="move_task",
                description="Move task to another project.",
                parameters={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "project_id": {"type": "string"},
                    },
                    "required": ["task_id", "project_id"],
                },
                handler=lambda task_id, project_id, **_: self.provider.move_task(
                    task_id=task_id,
                    project_id=project_id,
                ).model_dump(),
            )
        )
        self._register(
            ToolSpec(
                name="mark_complete",
                description="Mark a task as completed.",
                parameters={
                    "type": "object",
                    "properties": {"task_id": {"type": "string"}},
                    "required": ["task_id"],
                },
                handler=lambda task_id, **_: self.provider.mark_complete(task_id).model_dump(),
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

import json

from app.providers.mock.ticktick import MockTickTickProvider
from app.tools.registry import ToolRegistry


def test_create_subtasks_tool() -> None:
    registry = ToolRegistry(MockTickTickProvider())
    result = registry.execute_tool(
        "create_subtasks",
        json.dumps({"task_id": "task-1", "titles": ["Шаг 1", "Шаг 2"]}, ensure_ascii=False),
    )
    payload = json.loads(result)
    assert len(payload) == 2
    assert payload[0]["title"] == "Шаг 1"

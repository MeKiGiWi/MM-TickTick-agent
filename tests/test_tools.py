import json

from app.providers.mock.ticktick import MockTickTickProvider
from app.tools.registry import ToolRegistry


def test_create_task_tool_is_registered() -> None:
    registry = ToolRegistry(MockTickTickProvider())
    tools = registry.list_openrouter_tools()
    assert any(tool["function"]["name"] == "create_task" for tool in tools)


def test_create_task_tool_uses_mock_provider_defaults() -> None:
    registry = ToolRegistry(MockTickTickProvider())
    result = registry.execute_tool(
        "create_task",
        json.dumps({"title": "hello world"}, ensure_ascii=False),
    )
    payload = json.loads(result)
    assert payload["title"] == "hello world"
    assert payload["project_id"] == "inbox"


def test_create_subtasks_tool() -> None:
    registry = ToolRegistry(MockTickTickProvider())
    result = registry.execute_tool(
        "create_subtasks",
        json.dumps({"task_id": "task-1", "titles": ["Шаг 1", "Шаг 2"]}, ensure_ascii=False),
    )
    payload = json.loads(result)
    assert len(payload) == 2
    assert payload[0]["title"] == "Шаг 1"

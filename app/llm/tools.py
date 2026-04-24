from typing import Any, Protocol


class ToolExecutor(Protocol):
    def get_tool_schemas(self) -> list[dict[str, Any]]: ...

    def execute_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ToolHandler(Protocol):
    def __call__(self, **kwargs: Any) -> Any:
        ...


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def to_openrouter_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

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

    @classmethod
    def _sanitize_openrouter_schema(cls, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                if key in {"additionalProperties", "default"}:
                    continue
                sanitized[key] = cls._sanitize_openrouter_schema(item)
            return sanitized
        if isinstance(value, list):
            return [cls._sanitize_openrouter_schema(item) for item in value]
        return value

    def to_openrouter_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self._sanitize_openrouter_schema(self.parameters),
            },
        }

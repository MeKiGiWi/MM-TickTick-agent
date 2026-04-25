import json
import os
from typing import Any


class ToolDebugPrinter:
    SYSTEM_INFO_PROMPT = "ℹ️ system> "
    DEFAULT_MODE = "names"

    @staticmethod
    def pretty_json(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except TypeError:
            return str(value)

    @classmethod
    def extract_lines(
        cls,
        previous_messages: list[dict[str, object]],
        updated_messages: list[dict[str, object]],
        mode: str | None = None,
    ) -> list[str]:
        normalized_mode = (mode or cls.DEFAULT_MODE).strip().casefold()
        new_messages = updated_messages[len(previous_messages) :]
        lines: list[str] = []
        for message in new_messages:
            if message.get("role") == "assistant":
                for tool_call in message.get("tool_calls", []) or []:
                    function = tool_call.get("function", {})
                    name = function.get("name", "unknown")
                    arguments = function.get("arguments", "{}")
                    try:
                        parsed_arguments = json.loads(arguments)
                    except Exception:
                        parsed_arguments = arguments
                    lines.append(f"tool call: {name}")
                    if normalized_mode == "full":
                        lines.append(cls.pretty_json(parsed_arguments))
            elif message.get("role") == "tool":
                if normalized_mode == "full":
                    lines.append(f"tool result: {message.get('name', 'unknown')}")
                    content = message.get("content", "")
                    try:
                        parsed_content = json.loads(content) if isinstance(content, str) else content
                    except Exception:
                        parsed_content = content
                    lines.append(cls.pretty_json(parsed_content))
        return lines

    @classmethod
    def print_if_enabled(
        cls,
        enabled: bool,
        previous_messages: list[dict[str, object]],
        updated_messages: list[dict[str, object]],
    ) -> None:
        if not enabled:
            return
        mode = os.getenv("DEBUG_TOOL_FLOW_MODE", cls.DEFAULT_MODE)
        lines = cls.extract_lines(previous_messages, updated_messages, mode=mode)
        if not lines:
            return
        print()
        print(f"{cls.SYSTEM_INFO_PROMPT}tool flow")
        for line in lines:
            print(line)

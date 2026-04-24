from datetime import datetime
from typing import Any, Optional

from app.utils.timezone import resolve_timezone, timezone_label


class RuntimeContextBuilder:
    PREFIX = "Runtime context:"

    @classmethod
    def build_message(cls, user_timezone: Optional[str] = None) -> str:
        timezone = resolve_timezone(user_timezone)
        now = datetime.now(timezone)
        timezone_name = timezone_label(timezone)
        return (
            f"{cls.PREFIX} "
            f"Current local datetime is {now.isoformat()}. "
            f"Current local date is {now.date().isoformat()}. "
            f"Timezone is {timezone_name}. "
            "Use this as the source of truth for words like today, tomorrow, this week, and nearest week."
        )

    @classmethod
    def upsert(
        cls,
        messages: list[dict[str, object]],
        user_timezone: Optional[str] = None,
    ) -> list[dict[str, object]]:
        filtered: list[dict[str, object]] = []
        for message in messages:
            content = message.get("content")
            if (
                message.get("role") == "system"
                and isinstance(content, str)
                and content.startswith(cls.PREFIX)
            ):
                continue
            filtered.append(message)
        filtered.append({"role": "system", "content": cls.build_message(user_timezone)})
        return filtered

    @staticmethod
    def sanitize_text(value: str) -> str:
        if not any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            return value
        return value.encode("utf-8", "surrogateescape").decode("utf-8", "replace")

    @classmethod
    def sanitize_payload(cls, value: Any) -> Any:
        if isinstance(value, str):
            return cls.sanitize_text(value)
        if isinstance(value, list):
            return [cls.sanitize_payload(item) for item in value]
        if isinstance(value, dict):
            return {key: cls.sanitize_payload(item) for key, item in value.items()}
        return value

    @staticmethod
    def format_turn_error(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        lowered = message.lower()
        if "network error" in lowered or "dns" in lowered or "connection error" in lowered:
            return (
                f"Не удалось обработать ход из-за временной сетевой ошибки. Подробности: {message}"
            )
        return f"Не удалось обработать ход: {message}"

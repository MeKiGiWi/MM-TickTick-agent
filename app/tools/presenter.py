from __future__ import annotations

from datetime import date, datetime, timedelta, tzinfo
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.utils.timezone import resolve_timezone


class ToolPresenter:
    MONTHS_RU = {
        1: "января",
        2: "февраля",
        3: "марта",
        4: "апреля",
        5: "мая",
        6: "июня",
        7: "июля",
        8: "августа",
        9: "сентября",
        10: "октября",
        11: "ноября",
        12: "декабря",
    }

    def __init__(
        self,
        *,
        user_timezone: Optional[str] = None,
        now_provider: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.user_timezone = user_timezone
        self.now_provider = now_provider

    def _local_timezone(self) -> ZoneInfo | tzinfo:
        return resolve_timezone(self.user_timezone)

    def _now(self) -> datetime:
        timezone = self._local_timezone()
        current = self.now_provider() if self.now_provider else datetime.now(timezone)
        if current.tzinfo is None:
            return current.replace(tzinfo=timezone)
        return current.astimezone(timezone)

    @staticmethod
    def dump_item(item: Any) -> Any:
        if hasattr(item, "model_dump"):
            return item.model_dump()
        return item

    @staticmethod
    def tool_error(name: str, exc: Exception) -> dict[str, Any]:
        return {
            "error": {
                "tool": name,
                "message": str(exc),
            }
        }

    @staticmethod
    def task_timezone(payload: dict[str, Any], fallback: ZoneInfo | tzinfo) -> ZoneInfo | tzinfo:
        timezone_name = payload.get("time_zone")
        if isinstance(timezone_name, str) and timezone_name.strip():
            try:
                return ZoneInfo(timezone_name.strip())
            except ZoneInfoNotFoundError:
                return fallback
        return fallback

    @staticmethod
    def parse_ticktick_datetime(value: str) -> datetime | None:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    @classmethod
    def format_russian_date(cls, value: date, include_year: bool) -> str:
        result = f"{value.day} {cls.MONTHS_RU[value.month]}"
        if include_year:
            result = f"{result} {value.year}"
        return result

    @classmethod
    def relative_label(cls, target_date: date, current_date: date) -> Optional[str]:
        delta_days = (target_date - current_date).days
        if delta_days < 0:
            return "просрочено"
        if delta_days == 0:
            return "сегодня"
        if delta_days == 1:
            return "завтра"
        if delta_days == 2:
            return "послезавтра"
        current_week_start = current_date - timedelta(days=current_date.weekday())
        next_week_start = current_week_start + timedelta(days=7)
        next_week_end = next_week_start + timedelta(days=6)
        if next_week_start <= target_date <= next_week_end:
            return "на следующей неделе"
        return None

    @classmethod
    def humanize_localized_datetime(
        cls,
        localized: datetime,
        *,
        is_all_day: bool,
        current_date: date,
    ) -> tuple[str, Optional[str]]:
        target_date = localized.date()
        relative = cls.relative_label(target_date, current_date)
        include_year = target_date.year != current_date.year
        date_part = cls.format_russian_date(target_date, include_year)
        if relative == "просрочено":
            human = f"{date_part}, просрочено"
        elif relative:
            human = f"{relative}, {date_part}"
        else:
            human = date_part
        if not is_all_day:
            human = f"{human}, {localized.strftime('%H:%M')}"
        return human, relative

    def augment_task_payload(self, payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload
        fallback_timezone = self._local_timezone()
        task_timezone = self.task_timezone(payload, fallback_timezone)
        is_all_day = bool(payload.get("is_all_day"))
        current_date = self._now().astimezone(task_timezone).date()

        def augment(prefix: str) -> None:
            raw_value = payload.get(prefix)
            if not isinstance(raw_value, str) or not raw_value:
                return
            parsed = self.parse_ticktick_datetime(raw_value)
            if parsed is None:
                return
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=task_timezone)
            localized = parsed.astimezone(task_timezone)
            payload[f"{prefix}_display"] = (
                localized.date().isoformat() if is_all_day else localized.isoformat()
            )
            payload[f"{prefix}_display_date"] = localized.date().isoformat()
            payload[f"{prefix}_display_time"] = None if is_all_day else localized.strftime("%H:%M")
            human, relative = self.humanize_localized_datetime(
                localized,
                is_all_day=is_all_day,
                current_date=current_date,
            )
            payload[f"{prefix}_human"] = human
            payload[f"{prefix}_relative"] = relative
            if prefix == "due_date":
                payload["due_date_local"] = localized.isoformat()
                payload["due_date_local_date"] = localized.date().isoformat()
                payload["due_date_local_time"] = None if is_all_day else localized.strftime("%H:%M")

        augment("due_date")
        augment("start_date")
        return payload

    def present(self, result: Any) -> Any:
        if isinstance(result, list):
            return [self.augment_task_payload(self.dump_item(item)) for item in result]
        if isinstance(result, dict):
            return {key: self.present(value) for key, value in result.items()}
        return self.augment_task_payload(self.dump_item(result))

from datetime import date, datetime, time
from typing import Any, Optional
from zoneinfo import ZoneInfo


def parse_ticktick_datetime(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def format_ticktick_datetime(value: datetime) -> str:
    return value.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S%z")


def local_date_to_ticktick_all_day_datetime(local_date: date, timezone_name: str) -> str:
    timezone = ZoneInfo(timezone_name)
    local_dt = datetime.combine(local_date, time.min, tzinfo=timezone)
    return format_ticktick_datetime(local_dt)


def normalize_ticktick_datetime_input(value: str, timezone_name: str, is_all_day: bool) -> str:
    normalized = value.strip()
    parsed = parse_ticktick_datetime(normalized)
    if parsed is None:
        return normalized
    if parsed.tzinfo is not None:
        return parsed.strftime("%Y-%m-%dT%H:%M:%S%z")
    local_date = parsed.date()
    timezone = ZoneInfo(timezone_name)
    if is_all_day:
        return local_date_to_ticktick_all_day_datetime(local_date, timezone_name)
    local_dt = datetime.combine(local_date, time.min, tzinfo=timezone)
    return format_ticktick_datetime(local_dt)


def normalize_task_datetime_fields(
    payload: dict[str, Any],
    default_timezone_name: str,
) -> dict[str, Any]:
    normalized = dict(payload)
    timezone_name = str(normalized.get("timeZone") or default_timezone_name)
    is_all_day = bool(normalized.get("isAllDay"))
    for field_name in ("dueDate", "startDate"):
        value = normalized.get(field_name)
        if isinstance(value, str) and value.strip():
            normalized[field_name] = normalize_ticktick_datetime_input(
                value,
                timezone_name=timezone_name,
                is_all_day=is_all_day,
            )
    if is_all_day and "timeZone" not in normalized:
        normalized["timeZone"] = timezone_name
    return normalized


def normalize_status_filter(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    normalized = status.strip().casefold()
    if normalized in {"normal", "open"}:
        return "normal"
    if normalized in {"completed", "done"}:
        return "completed"
    raise ValueError(f"Неподдерживаемый статус задач: {status}")


def normalize_completion_status(status: object) -> str:
    normalized = str(status).strip().casefold()
    if normalized in {"completed", "done"}:
        return "completed"
    if normalized in {"normal", "open"}:
        raise ValueError(
            "update_task не поддерживает перевод задачи в open/normal. "
            "Для завершения используйте status='completed' или tool mark_complete."
        )
    raise ValueError(f"Неподдерживаемый статус обновления задачи: {status}")

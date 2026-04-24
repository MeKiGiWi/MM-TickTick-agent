import os
from datetime import datetime, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def configured_timezone_name(configured: Optional[str] = None) -> Optional[str]:
    for candidate in (configured, os.getenv("APP_TIMEZONE"), os.getenv("TZ")):
        normalized = (candidate or "").strip()
        if normalized:
            return normalized
    return None


def resolve_timezone(configured: Optional[str] = None) -> ZoneInfo | tzinfo:
    configured_name = configured_timezone_name(configured)
    if configured_name:
        try:
            return ZoneInfo(configured_name)
        except ZoneInfoNotFoundError:
            pass
    return datetime.now().astimezone().tzinfo or ZoneInfo("UTC")


def timezone_label(timezone: ZoneInfo | tzinfo) -> str:
    key = getattr(timezone, "key", None)
    if isinstance(key, str) and key:
        return key
    return datetime.now(timezone).tzname() or "local"

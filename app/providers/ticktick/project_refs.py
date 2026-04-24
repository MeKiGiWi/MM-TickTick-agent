import re
from typing import Literal, Optional


INBOX_PROJECT_ALIASES = {"", "default", "inbox", "inbox_id", "none"}
_ALIAS_SPLIT_PATTERN = re.compile(r"\s*(?:/|,|\|)\s*")

ProjectRefKind = Literal["inbox", "id", "name"]


def _normalize_text(value: Optional[str]) -> str:
    return (value or "").strip()


def is_default_project_alias(value: str) -> bool:
    return _normalize_text(value).casefold() in INBOX_PROJECT_ALIASES


def normalize_project_ref(project_ref: Optional[str]) -> Optional[str]:
    normalized = _normalize_text(project_ref)
    if not normalized:
        return "inbox"
    if is_default_project_alias(normalized):
        return "inbox"
    tokens = [token.strip() for token in _ALIAS_SPLIT_PATTERN.split(normalized) if token.strip()]
    if tokens and all(is_default_project_alias(token) for token in tokens):
        return "inbox"
    return normalized


def classify_project_ref(project_ref: Optional[str]) -> ProjectRefKind:
    normalized = normalize_project_ref(project_ref)
    if normalized == "inbox":
        return "inbox"
    if normalized and normalized.casefold().startswith("inbox"):
        return "id"
    if normalized and re.fullmatch(r"[A-Za-z0-9_-]{8,}", normalized):
        return "id"
    return "name"

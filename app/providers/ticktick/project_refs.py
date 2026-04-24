import re
from typing import Optional


INBOX_PROJECT_ALIASES = {"inbox", "default"}
_ALIAS_SPLIT_PATTERN = re.compile(r"\s*(?:/|,|\|)\s*")


def is_default_project_alias(value: str) -> bool:
    return value.strip().casefold() in INBOX_PROJECT_ALIASES


def normalize_project_ref(project_ref: Optional[str]) -> Optional[str]:
    if project_ref is None:
        return None
    normalized = project_ref.strip()
    if not normalized:
        return None
    if is_default_project_alias(normalized):
        return "inbox"
    tokens = [token.strip() for token in _ALIAS_SPLIT_PATTERN.split(normalized) if token.strip()]
    if len(tokens) > 1 and all(is_default_project_alias(token) for token in tokens):
        return "inbox"
    return normalized

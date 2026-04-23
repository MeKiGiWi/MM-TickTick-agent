from __future__ import annotations

from pathlib import Path

from app.domain.models import TickTickCredentials
from app.providers.mock.ticktick import MockTickTickProvider
from app.providers.ticktick.base import TickTickProvider
from app.providers.ticktick.client import TickTickApiProvider


def build_ticktick_provider(credentials: TickTickCredentials, root: Path) -> TickTickProvider:
    if credentials.provider == "ticktick":
        return TickTickApiProvider(
            credentials=credentials,
            guide_path=root / "ticktick_open_api_codex_guide.md",
        )
    return MockTickTickProvider()

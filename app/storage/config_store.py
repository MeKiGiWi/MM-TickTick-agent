from pathlib import Path

from app.domain.models import AppConfig
from app.utils.json import dump_json, load_json


class ConfigStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "config.local.json"

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> AppConfig:
        return AppConfig.model_validate(load_json(self.path))

    def save(self, config: AppConfig) -> None:
        dump_json(self.path, config.model_dump())

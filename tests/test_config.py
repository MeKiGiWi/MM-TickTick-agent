from pathlib import Path

from app.config.setup import ensure_config


def test_setup_creates_local_config(monkeypatch, tmp_path: Path) -> None:
    answers = iter(
        [
            "or-test-key",
            "",
            "mock",
            "",
            "",
            "",
            "",
            "",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    config = ensure_config(tmp_path)
    assert config.openrouter.api_key == "or-test-key"
    assert (tmp_path / "config.local.json").exists()

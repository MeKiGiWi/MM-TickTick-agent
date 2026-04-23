from __future__ import annotations

from typing import Any

from app.domain.models import TickTickCredentials
from app.providers.ticktick.oauth import TickTickOAuthClient, run_oauth_login


class FakeOAuthClient(TickTickOAuthClient):
    def __init__(self) -> None:
        self.exchanged_payload: dict[str, Any] = {}

    def build_authorization_url(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
    ) -> str:
        return (
            f"https://ticktick.com/oauth/authorize?client_id={client_id}"
            f"&redirect_uri={redirect_uri}&scope={scope}&state={state}"
        )

    def exchange_code_for_token(
        self,
        *,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
        scope: str,
    ) -> str:
        self.exchanged_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": scope,
        }
        return "ticktick-token"


def test_run_oauth_login_accepts_manual_code(monkeypatch) -> None:
    credentials = TickTickCredentials(
        provider="ticktick",
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="https://example.com/callback",
    )
    monkeypatch.setattr("builtins.input", lambda _: "oauth-code")
    result = run_oauth_login(credentials, oauth_client=FakeOAuthClient(), open_browser=False)
    assert result.access_token == "ticktick-token"
    assert result.state


def test_ensure_config_runs_oauth_for_ticktick(monkeypatch, tmp_path) -> None:
    from app.config.setup import ensure_config

    answers = iter(
        [
            "or-test-key",
            "",
            "ticktick",
            "client-id",
            "client-secret",
            "https://example.com/callback",
            "",
            "inbox",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(answers))

    class DummyOAuthResult:
        access_token = "saved-token"
        state = "saved-state"

    monkeypatch.setattr("app.config.setup.run_oauth_login", lambda credentials: DummyOAuthResult())
    config = ensure_config(tmp_path)
    assert config.ticktick.access_token == "saved-token"
    assert config.ticktick.auth_state == "saved-state"

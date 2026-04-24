from __future__ import annotations

from typing import Any

from app.domain.models import TickTickCredentials
from app.providers.ticktick.oauth import (
    TickTickOAuthClient,
    _resolve_callback_bind_host,
    run_oauth_login,
)


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


def test_run_oauth_login_accepts_full_redirect_url(monkeypatch) -> None:
    credentials = TickTickCredentials(
        provider="ticktick",
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="https://example.com/callback",
    )
    oauth_client = FakeOAuthClient()
    monkeypatch.setattr(
        "builtins.input",
        lambda _: "https://example.com/callback?code=oauth-code&state=fixed-state",
    )
    monkeypatch.setattr(
        "app.providers.ticktick.oauth.secrets.token_urlsafe", lambda _: "fixed-state"
    )
    result = run_oauth_login(credentials, oauth_client=oauth_client, open_browser=False)
    assert result.access_token == "ticktick-token"
    assert oauth_client.exchanged_payload["code"] == "oauth-code"


def test_run_oauth_login_prefers_automatic_callback(monkeypatch) -> None:
    credentials = TickTickCredentials(
        provider="ticktick",
        client_id="client-id",
        client_secret="client-secret",
        redirect_uri="http://localhost:8765/callback",
    )
    oauth_client = FakeOAuthClient()
    monkeypatch.setattr(
        "app.providers.ticktick.oauth._wait_for_callback",
        lambda redirect_uri, timeout_seconds=120.0: {
            "code": "oauth-code",
            "state": "fixed-state",
        },
    )
    monkeypatch.setattr(
        "app.providers.ticktick.oauth.secrets.token_urlsafe", lambda _: "fixed-state"
    )
    monkeypatch.setattr(
        "builtins.input",
        lambda _: (_ for _ in ()).throw(AssertionError("manual input should not be used")),
    )
    result = run_oauth_login(
        credentials,
        oauth_client=oauth_client,
        open_browser=False,
    )
    assert result.access_token == "ticktick-token"
    assert oauth_client.exchanged_payload["code"] == "oauth-code"


def test_oauth_callback_bind_host_is_docker_friendly(monkeypatch) -> None:
    monkeypatch.setattr("app.providers.ticktick.oauth._is_container_environment", lambda: True)
    assert _resolve_callback_bind_host("http://localhost:8765/callback") == "0.0.0.0"
    assert _resolve_callback_bind_host("http://127.0.0.1:8765/callback") == "0.0.0.0"


def test_ensure_config_runs_oauth_for_ticktick(monkeypatch, tmp_path) -> None:
    from app.config.setup import ensure_config

    answers = iter(
        [
            "or-test-key",
            "qwen/qwen-turbo",
            "",
            "ticktick",
            "client-id",
            "client-secret",
            "https://example.com/callback",
            "tasks:write tasks:read",
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


def test_ensure_config_prompts_for_ticktick_credentials(monkeypatch, tmp_path) -> None:
    from app.config.setup import ensure_config

    answers = iter(
        [
            "or-test-key",
            "qwen/qwen-turbo",
            "",
            "ticktick",
            "prompt-client-id",
            "prompt-client-secret",
            "https://example.com/callback",
            "tasks:write tasks:read",
            "inbox",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    captured_credentials: dict[str, str] = {}

    class DummyOAuthResult:
        access_token = "saved-token"
        state = "saved-state"

    def fake_login(credentials):
        captured_credentials["client_id"] = credentials.client_id
        captured_credentials["client_secret"] = credentials.client_secret
        captured_credentials["redirect_uri"] = credentials.redirect_uri
        return DummyOAuthResult()

    monkeypatch.setattr("app.config.setup.run_oauth_login", fake_login)
    config = ensure_config(tmp_path)
    assert config.ticktick.access_token == "saved-token"
    assert captured_credentials == {
        "client_id": "prompt-client-id",
        "client_secret": "prompt-client-secret",
        "redirect_uri": "https://example.com/callback",
    }


def test_ensure_config_existing_ticktick_config_without_token_runs_oauth(
    monkeypatch, tmp_path
) -> None:
    from app.config.setup import ensure_config
    from app.domain.models import AppConfig, OpenRouterConfig
    from app.storage.config_store import ConfigStore

    store = ConfigStore(tmp_path)
    store.save(
        AppConfig(
            openrouter=OpenRouterConfig(api_key="or-test-key"),
            ticktick=TickTickCredentials(
                provider="ticktick",
                client_id="client-id",
                client_secret="client-secret",
                redirect_uri="https://example.com/callback",
            ),
        )
    )

    class DummyOAuthResult:
        access_token = "saved-token"
        state = "saved-state"

    monkeypatch.setattr("app.config.setup.run_oauth_login", lambda credentials: DummyOAuthResult())
    config = ensure_config(tmp_path)
    assert config.ticktick.access_token == "saved-token"


def test_ensure_config_existing_ticktick_config_with_token_skips_oauth(
    monkeypatch, tmp_path
) -> None:
    from app.config.setup import ensure_config
    from app.domain.models import AppConfig, OpenRouterConfig
    from app.storage.config_store import ConfigStore

    store = ConfigStore(tmp_path)
    store.save(
        AppConfig(
            openrouter=OpenRouterConfig(api_key="or-test-key"),
            ticktick=TickTickCredentials(
                provider="ticktick",
                client_id="client-id",
                client_secret="client-secret",
                redirect_uri="https://example.com/callback",
                access_token="existing-token",
            ),
        )
    )

    def fail_login(_credentials):
        raise AssertionError("OAuth should not run when access token already exists")

    monkeypatch.setattr("app.config.setup.run_oauth_login", fail_login)
    config = ensure_config(tmp_path)
    assert config.ticktick.access_token == "existing-token"

import base64
import os
import secrets
import sys
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from app.domain.models import TickTickCredentials


AUTH_URL = "https://ticktick.com/oauth/authorize"
TOKEN_URL = "https://ticktick.com/oauth/token"
DEFAULT_SCOPE = "tasks:write tasks:read"


@dataclass
class TickTickOAuthResult:
    access_token: str
    state: str


class TickTickOAuthClient:
    def __init__(self) -> None:
        self.client = httpx.Client(timeout=30.0)

    def build_authorization_url(
        self,
        *,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
    ) -> str:
        query = urlencode(
            {
                "scope": scope,
                "client_id": client_id,
                "state": state,
                "redirect_uri": redirect_uri,
                "response_type": "code",
            }
        )
        return f"{AUTH_URL}?{query}"

    def exchange_code_for_token(
        self,
        *,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
        scope: str,
    ) -> str:
        basic_token = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode(
            "ascii"
        )
        response = self.client.post(
            TOKEN_URL,
            headers={
                "Authorization": f"Basic {basic_token}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={
                "code": code,
                "grant_type": "authorization_code",
                "scope": scope,
                "redirect_uri": redirect_uri,
            },
        )
        response.raise_for_status()
        payload = response.json()
        access_token = payload.get("access_token", "")
        if not access_token:
            raise ValueError("TickTick OAuth не вернул access_token")
        return access_token


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    server_version = "TickTickOAuth/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        self.server.oauth_params = {key: values[0] for key, values in params.items()}
        body = (
            "TickTick login completed. You can return to the terminal and close this tab."
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


class OAuthCallbackServer(HTTPServer):
    oauth_params: Dict[str, str]


def _is_container_environment() -> bool:
    if os.getenv("DOTENV_RUNNING_IN_CONTAINER") == "1":
        return True
    if Path("/.dockerenv").exists():
        return True
    return False


def _can_open_browser() -> bool:
    if _is_container_environment():
        return False
    if os.name == "nt" or sys.platform == "darwin":
        return True
    return bool(os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"))


def _resolve_callback_bind_host(redirect_uri: str) -> Optional[str]:
    parsed = urlparse(redirect_uri)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or not parsed.port:
        return None
    if _is_container_environment():
        return "0.0.0.0"
    return parsed.hostname


def _wait_for_callback(
    redirect_uri: str, timeout_seconds: float = 120.0
) -> Optional[Dict[str, str]]:
    parsed = urlparse(redirect_uri)
    bind_host = _resolve_callback_bind_host(redirect_uri)
    if bind_host is None:
        return None

    try:
        server = OAuthCallbackServer((bind_host, parsed.port), _OAuthCallbackHandler)
    except OSError:
        return None
    server.oauth_params = {}
    server.timeout = 1.0
    stop_event = threading.Event()

    def serve() -> None:
        while not stop_event.is_set() and not server.oauth_params:
            server.handle_request()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    stop_event.set()
    server.server_close()
    if not server.oauth_params:
        return None
    return server.oauth_params


def run_oauth_login(
    credentials: TickTickCredentials,
    *,
    oauth_client: Optional[TickTickOAuthClient] = None,
    open_browser: bool = True,
    callback_timeout_seconds: float = 120.0,
) -> TickTickOAuthResult:
    if not credentials.client_id or not credentials.client_secret or not credentials.redirect_uri:
        raise ValueError("Для TickTick OAuth нужны client_id, client_secret и redirect_uri")

    client = oauth_client or TickTickOAuthClient()
    state = secrets.token_urlsafe(16)
    scope = credentials.scope or DEFAULT_SCOPE
    auth_url = client.build_authorization_url(
        client_id=credentials.client_id,
        redirect_uri=credentials.redirect_uri,
        scope=scope,
        state=state,
    )

    print("\nTickTick OAuth login")
    print(
        "Для реального входа нужен TickTick Developer app с client_id, client_secret и redirect_uri."
    )
    print(f"Откройте ссылку и подтвердите доступ:\n{auth_url}\n")

    parsed = urlparse(credentials.redirect_uri)
    callback_params: Optional[Dict[str, str]] = None
    if parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port:
        if open_browser and _can_open_browser():
            webbrowser.open(auth_url)
        elif open_browser:
            print("Авто-открытие браузера пропущено: похоже, это container/headless среда.")
        if _is_container_environment():
            print(
                "Подсказка: для автоматического localhost callback в Docker используйте "
                "`docker compose run --rm --service-ports app` "
                "или `docker compose up app`."
            )
        print(f"Жду callback на {credentials.redirect_uri}")
        callback_params = _wait_for_callback(
            credentials.redirect_uri,
            timeout_seconds=callback_timeout_seconds,
        )
        if callback_params is None:
            print("Callback не сработал автоматически.")

    if callback_params is None:
        callback_value = input(
            "Если callback не сработал, вставьте полный redirect URL или code: "
        ).strip()
        if callback_value.startswith("http://") or callback_value.startswith("https://"):
            parsed_callback = urlparse(callback_value)
            callback_params = {
                key: values[0] for key, values in parse_qs(parsed_callback.query).items()
            }
        else:
            callback_params = {"code": callback_value, "state": state}

    returned_state = callback_params.get("state", "")
    if returned_state and returned_state != state:
        raise ValueError("TickTick OAuth state mismatch")

    code = callback_params.get("code", "")
    if not code:
        raise ValueError("TickTick OAuth не вернул code")

    access_token = client.exchange_code_for_token(
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
        code=code,
        redirect_uri=credentials.redirect_uri,
        scope=scope,
    )
    return TickTickOAuthResult(access_token=access_token, state=state)

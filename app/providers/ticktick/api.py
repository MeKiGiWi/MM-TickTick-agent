from typing import Any

import httpx

from app.domain.models import TickTickCredentials


class TickTickApiClient:
    def __init__(self, credentials: TickTickCredentials) -> None:
        self.credentials = credentials
        self.base_url = "https://api.ticktick.com/open/v1"
        self.client = self._build_client()

    def _build_client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.credentials.access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    @staticmethod
    def _format_request_error(exc: httpx.RequestError, method: str, path: str) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        lowered = message.lower()
        if "name or service not known" in lowered or "nodename nor servname provided" in lowered:
            detail = "ошибка DNS-разрешения имени"
        elif "temporary failure in name resolution" in lowered:
            detail = "временная ошибка DNS-разрешения имени"
        elif "timed out" in lowered or isinstance(exc, httpx.TimeoutException):
            detail = "таймаут соединения"
        else:
            detail = message
        return f"TickTick network error during {method} {path}: {detail}"

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        last_error: httpx.RequestError | None = None
        for attempt in range(3):
            try:
                response = self.client.request(method, path, **kwargs)
                break
            except httpx.RequestError as exc:
                last_error = exc
                if attempt == 0:
                    self.client.close()
                    self.client = self._build_client()
                if attempt == 2:
                    raise ValueError(self._format_request_error(exc, method, path)) from exc
        else:
            if last_error is not None:
                raise ValueError(
                    self._format_request_error(last_error, method, path)
                ) from last_error
            raise ValueError(f"TickTick network error during {method} {path}")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = response.text.strip()
            body_suffix = f": {body}" if body else ""
            raise ValueError(
                f"TickTick API error {response.status_code} {method} {path}{body_suffix}"
            ) from exc
        if not response.content:
            return {}
        return response.json()

"""
HTTP client for the CodeGuardian FastAPI server.

All commands in connected mode route through this module.
Server errors and connection failures are translated into
user-friendly RuntimeError / ConnectionError messages.
"""

from __future__ import annotations

import json
from typing import Any, Generator

import httpx

_CONNECT_REFUSED = (
    "Server not running. Start it with [bold cyan]cgctl serve[/bold cyan] "
    "or use [bold]--offline[/bold] mode."
)


class CGClient:
    """Thin synchronous wrapper around httpx for the CodeGuardian API."""

    def __init__(self, base_url: str = "http://localhost:8742", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ── Internal helpers ──────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _handle_http_error(self, exc: httpx.HTTPStatusError) -> None:
        body = exc.response.text[:300]
        raise RuntimeError(
            f"API returned {exc.response.status_code}: {body}"
        ) from exc

    # ── Public API ────────────────────────────────────────────────────────

    def get(self, path: str) -> dict[str, Any]:
        """Synchronous GET — raises ConnectionError or RuntimeError."""
        try:
            with httpx.Client(timeout=self.timeout) as c:
                resp = c.get(self._url(path))
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError as exc:
            raise ConnectionError(_CONNECT_REFUSED) from exc
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc)
            raise  # unreachable; satisfies type checker

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Synchronous POST — raises ConnectionError or RuntimeError."""
        try:
            with httpx.Client(timeout=self.timeout) as c:
                resp = c.post(self._url(path), json=payload)
                resp.raise_for_status()
                return resp.json()
        except httpx.ConnectError as exc:
            raise ConnectionError(_CONNECT_REFUSED) from exc
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc)
            raise

    def stream_post(
        self, path: str, payload: dict[str, Any]
    ) -> Generator[dict[str, Any], None, None]:
        """
        Streaming POST that yields parsed SSE event dicts.

        Events with ``data:`` prefix are JSON-decoded and yielded.
        Non-data lines (comments, empty) are silently skipped.
        Raises ConnectionError on refused connection.
        """
        try:
            with httpx.Client(timeout=self.timeout) as c:
                with c.stream("POST", self._url(path), json=payload) as resp:
                    resp.raise_for_status()
                    for raw in resp.iter_lines():
                        if not raw.startswith("data:"):
                            continue
                        text = raw[5:].strip()
                        if not text:
                            continue
                        try:
                            yield json.loads(text)
                        except json.JSONDecodeError:
                            pass
        except httpx.ConnectError as exc:
            raise ConnectionError(_CONNECT_REFUSED) from exc
        except httpx.HTTPStatusError as exc:
            self._handle_http_error(exc)


def make_client() -> CGClient:
    """Create a client using the current global state's api_url."""
    from cgctl.state import get_state

    s = get_state()
    return CGClient(base_url=s.api_url)


def is_offline() -> bool:
    from cgctl.state import get_state

    return get_state().offline

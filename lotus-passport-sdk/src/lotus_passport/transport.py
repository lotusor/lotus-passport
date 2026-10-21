"""Pluggable HTTP layer.

The client never imports ``requests`` directly. Everything goes through this
protocol, which buys three things:

1. tests run fully offline with a stub transport (no local server, no sockets);
2. async / httpx / aiohttp users can plug their own without forking the SDK;
3. apps that already own a tuned ``Session`` (retries, proxies, mTLS, tracing)
   can hand it over instead of the SDK creating a second connection pool.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .errors import PassportServiceError


@runtime_checkable
class Transport(Protocol):
    """Minimal HTTP surface the SDK needs."""

    def get_json(
        self, url: str, *, headers: dict[str, str] | None = None, timeout: float = 5.0
    ) -> tuple[int, Any]:
        """GET ``url`` and return ``(status_code, parsed_json_or_None)``."""

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 5.0,
    ) -> tuple[int, Any]:
        """POST JSON to ``url`` and return ``(status_code, parsed_json_or_None)``."""


class RequestsTransport:
    """Default transport backed by ``requests``.

    A single :class:`requests.Session` is reused so JWKS refreshes and userinfo
    calls ride keep-alive connections instead of paying a TLS handshake each time.
    """

    def __init__(self, session: Any | None = None) -> None:
        if session is None:
            try:
                import requests  # local import: keeps `requests` an optional dep
            except ImportError as exc:  # pragma: no cover - dependency guard
                raise PassportServiceError(
                    "requests is not installed. Either `pip install lotus-passport-sdk[requests]` "
                    "or pass your own transport=..."
                ) from exc
            session = requests.Session()
            session.headers.update({"User-Agent": "lotus-passport-sdk/1.0"})
        self._session = session

    # -- helpers ----------------------------------------------------------- #
    @staticmethod
    def _parse(resp: Any) -> tuple[int, Any]:
        try:
            return resp.status_code, resp.json()
        except ValueError:
            # Non-JSON body (nginx HTML error page, truncated response, ...).
            # Surface the status so the caller can distinguish 502 from 200-garbage.
            return resp.status_code, None

    # -- Transport protocol ------------------------------------------------ #
    def get_json(
        self, url: str, *, headers: dict[str, str] | None = None, timeout: float = 5.0
    ) -> tuple[int, Any]:
        try:
            resp = self._session.get(url, headers=headers, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - normalise every network failure
            raise PassportServiceError(f"GET {url} failed: {exc}") from exc
        return self._parse(resp)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 5.0,
    ) -> tuple[int, Any]:
        try:
            resp = self._session.post(url, json=payload, headers=headers, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            raise PassportServiceError(f"POST {url} failed: {exc}") from exc
        return self._parse(resp)


__all__ = ["Transport", "RequestsTransport"]

"""
Safe handling of the OAuth ``redirect_uri`` to prevent open-redirect abuse.

The login endpoint lets an integrating app pass ``?redirect_uri=...`` so the
passport can bounce the user (with tokens in the URL fragment) back to the
app's own callback page after a successful login. If that value were accepted
blindly, an attacker could craft

    /api/v1/oauth/github/login/?redirect_uri=https://evil.example.com/phish

and, after the victim logs in, land them on an attacker page carrying the
fresh tokens in the fragment — a classic open redirect / token leakage.

We therefore only honour a ``redirect_uri`` that is either
  * empty (the caller falls back to a JSON response), or
  * a localhost origin while DEBUG/TESTING (zero-config local dev, mirroring the
    CORS behaviour), or
  * explicitly listed in settings.OAUTH_ALLOWED_REDIRECT_URIS (production).

The same check is applied at login time (where the value is stored in the
OAuth ``state``) and re-applied at callback time (defence in depth).
"""
from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings


def _is_localhost(host: str | None) -> bool:
    return host in ("localhost", "127.0.0.1", "::1")


def is_redirect_uri_allowed(uri: str) -> bool:
    """Return True if ``uri`` may be used as a post-login redirect target.

    Allow-list entries in ``OAUTH_ALLOWED_REDIRECT_URIS`` match as follows:
      * origin-only (e.g. ``https://app.example.com``)  -> any path on that origin
      * with a path (e.g. ``https://app.example.com/cb``) -> exact match
    Trailing slashes are ignored for the comparison.
    """
    if not uri:
        return True
    try:
        parsed = urlparse(uri)
    except Exception:  # noqa: BLE001
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if getattr(settings, "DEBUG", False) or getattr(settings, "TESTING", False):
        # Local dev never needs an explicit allow-list entry.
        if _is_localhost(parsed.hostname):
            return True

    allowed = getattr(settings, "OAUTH_ALLOWED_REDIRECT_URIS", []) or []
    candidate_origin = f"{parsed.scheme}://{parsed.netloc}"
    for entry in allowed:
        entry = (entry or "").strip()
        if not entry:
            continue
        e = urlparse(entry)
        if e.scheme not in ("http", "https"):
            continue
        if e.path in ("", "/"):
            # Origin-only allow-list entry: matches any path under this origin.
            if candidate_origin == f"{e.scheme}://{e.netloc}":
                return True
        else:
            # Exact full-URI match (ignore trailing slash differences).
            if uri.rstrip("/") == entry.rstrip("/"):
                return True
    return False


def _origin_of(uri: str) -> str:
    parsed = urlparse(uri)
    return f"{parsed.scheme}://{parsed.netloc}"


def is_external_oauth_redirect(uri: str) -> bool:
    """True when ``uri`` points at a *third-party* integrating app (not the
    passport's own first-party SPA), meaning the OAuth authorization-consent
    screen should be shown before bouncing the token back.

    First-party origins are the passport SPA / API themselves. In DEBUG we also
    treat the local dev origins as first-party so the dev login loop stays
    seamless (the consent screen is a production external-app concern).
    """
    origin = _origin_of(uri)
    first_party = set(getattr(settings, "OAUTH_FIRST_PARTY_ORIGINS", []) or [])
    if getattr(settings, "DEBUG", False):
        first_party.update(
            {
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
            }
        )
    return origin not in first_party


def resolve_oauth_client(redirect_uri: str) -> dict:
    """Map a redirect_uri to display info for the authorization-consent screen.

    Known clients are configured in ``settings.OAUTH_CLIENTS`` keyed by origin.
    Unknown origins fall back to a generic entry derived from the host.
    """
    origin = _origin_of(redirect_uri)
    clients = getattr(settings, "OAUTH_CLIENTS", {}) or {}
    if origin in clients:
        info = dict(clients[origin])
        info["origin"] = origin
        return info
    return {
        "name": urlparse(redirect_uri).netloc,
        "origin": origin,
        "logo": "",
        "scopes": ["读取你的昵称、头像等基本资料（用于登录该应用）"],
    }

"""Value objects returned by the SDK.

``PassportIdentity`` is deliberately identity-only. Lotus Passport never stores
business data (school, roles, scores) — the integrating app owns that and joins
on :attr:`PassportIdentity.passport_user_id`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class PassportIdentity:
    """A verified Lotus Passport identity.

    Attributes:
        passport_user_id: Stable UUID string. **This is the join key** — store it
            on your local user row (unique, indexed). Never key off ``email``:
            users change it, and two providers can report the same address.
        email: May be empty — some providers (WeChat) never expose one.
        nickname: Display name, may be empty.
        avatar: Avatar URL, only populated by ``get_userinfo()``.
        providers: Linked OAuth providers, only populated by ``get_userinfo()``.
        claims: Raw verified JWT payload, for anything the dataclass omits.
        source: ``"jwt"`` (offline verification) or ``"userinfo"`` (live call).
    """

    passport_user_id: str
    email: str = ""
    nickname: str = ""
    avatar: str = ""
    providers: tuple[str, ...] = ()
    claims: dict[str, Any] = field(default_factory=dict, repr=False)
    source: str = "jwt"

    @property
    def expires_at(self) -> datetime | None:
        """UTC expiry of the underlying token, if the ``exp`` claim was present."""
        exp = self.claims.get("exp")
        if exp is None:
            return None
        return datetime.fromtimestamp(int(exp), tz=timezone.utc)

    @classmethod
    def from_claims(cls, claims: dict[str, Any]) -> "PassportIdentity":
        """Build an identity from a *already verified* JWT payload."""
        return cls(
            passport_user_id=str(claims.get("passport_user_id", "")),
            email=claims.get("email") or "",
            nickname=claims.get("nickname") or "",
            claims=claims,
            source="jwt",
        )

    @classmethod
    def from_userinfo(
        cls, data: dict[str, Any], claims: dict[str, Any] | None = None
    ) -> "PassportIdentity":
        """Build an identity from a ``/api/v1/userinfo/`` response body."""
        return cls(
            passport_user_id=str(data.get("passport_user_id", "")),
            email=data.get("email") or "",
            nickname=data.get("nickname") or "",
            avatar=data.get("avatar") or "",
            providers=tuple(data.get("providers") or ()),
            claims=claims or {},
            source="userinfo",
        )


@dataclass(frozen=True)
class TokenPair:
    """Result of a refresh call."""

    access: str
    refresh: str = ""
    token_type: str = "Bearer"


__all__ = ["PassportIdentity", "TokenPair"]

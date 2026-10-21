"""Framework adapters.

Nothing is imported eagerly: ``import lotus_passport`` must not pull in FastAPI,
Django or Flask. Import the adapter you actually need::

    from lotus_passport.integrations.fastapi import PassportAuth
    from lotus_passport.integrations.drf import PassportAuthentication
    from lotus_passport.integrations.flask import passport_required
"""
from __future__ import annotations

__all__: list[str] = []

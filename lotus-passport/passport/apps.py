"""App config — wires the kid-aware JWT backend and safety checks at startup."""
from django.apps import AppConfig


class PassportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "passport"

    def ready(self) -> None:
        # simplejwt 5.x has no TOKEN_BACKEND setting, so its global
        # `state.token_backend` is hard-wired to a single-key TokenBackend.
        # Replace it with our kid-aware backend so RS256 key rotation works
        # (tokens signed by a still-valid previous key keep verifying).
        from django.conf import settings
        from rest_framework_simplejwt import state as jwt_state
        from rest_framework_simplejwt.settings import api_settings

        from .jwt import PassportTokenBackend

        jwt_state.token_backend = PassportTokenBackend(
            algorithm=api_settings.ALGORITHM,
            signing_key=settings.JWT_SIGNING_KEY,
            verifying_key=settings.JWT_VERIFYING_KEY,
            audience=api_settings.AUDIENCE,
            issuer=api_settings.ISSUER,
            jwk_url=api_settings.JWK_URL,
            leeway=api_settings.LEEWAY,
            json_encoder=api_settings.JSON_ENCODER,
        )

        # Register production safety system checks (import has side effects).
        import passport.checks  # noqa: F401

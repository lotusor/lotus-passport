"""Root URL configuration for Lotus Passport."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, re_path

from passport import dev_views, views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", views.health_check, name="health"),
    path(
        "api/v1/oauth/<str:provider>/login/",
        views.OAuthLoginView.as_view(),
        name="oauth-login",
    ),
    path(
        "api/v1/oauth/<str:provider>/callback/",
        views.OAuthCallbackView.as_view(),
        name="oauth-callback",
    ),
    # QQ 互联（腾讯开放平台）回调地址校验器拒绝以 "/" 结尾的 URL，
    # 故额外接受不带尾斜杠的形式：控制台注册用无尾斜杠地址，QQ 回跳也能命中。
    path(
        "api/v1/oauth/<str:provider>/callback",
        views.OAuthCallbackView.as_view(),
        name="oauth-callback-noslash",
    ),
    path(
        "api/v1/oauth/<str:provider>/bind/",
        views.OAuthBindView.as_view(),
        name="oauth-bind",
    ),
    # List must precede the <provider> catch-all below, else "accounts" is
    # mistaken for a provider name.
    path(
        "api/v1/oauth/accounts/",
        views.OAuthAccountsView.as_view(),
        name="oauth-accounts",
    ),
    path(
        "api/v1/oauth/<str:provider>/",
        views.OAuthUnbindView.as_view(),
        name="oauth-unbind",
    ),
    path("api/v1/userinfo/", views.UserInfoView.as_view(), name="userinfo"),
    path("api/v1/logout/", views.LogoutView.as_view(), name="logout"),
    path("api/v1/token/refresh/", views.TokenRefreshView.as_view(), name="token-refresh"),
    # Account management (§9.1 / §9.3 / §9.4d / §9.4e)
    path("api/v1/profile/", views.ProfileView.as_view(), name="profile"),
    # 头像本地上传（§9.1）：multipart，≤128KB，返回最新 UserInfo
    path(
        "api/v1/profile/avatar/",
        views.AvatarUploadView.as_view(),
        name="avatar-upload",
    ),
    path("api/v1/devices/", views.DeviceListView.as_view(), name="device-list"),
    path("api/v1/devices/<int:pk>/", views.DeviceDetailView.as_view(), name="device-detail"),
    path("api/v1/sessions/", views.SessionListView.as_view(), name="session-list"),
    path("api/v1/sessions/<int:pk>/", views.SessionDetailView.as_view(), name="session-detail"),
    path(
        "api/v1/security/login-history/",
        views.LoginHistoryView.as_view(),
        name="login-history",
    ),
    # Password login (§9.4a) — public auth endpoint
    path("api/v1/login/", views.PasswordLoginView.as_view(), name="password-login"),
    # Account security factors (§9.4a 密码)
    path(
        "api/v1/security/password/",
        views.PasswordStatusView.as_view(),
        name="password-status",
    ),
    path(
        "api/v1/security/password/change/",
        views.PasswordChangeView.as_view(),
        name="password-change",
    ),
    # Passkeys / WebAuthn (§9.4b)
    path(
        "api/v1/security/passkeys/",
        views.PasskeyListView.as_view(),
        name="passkey-list",
    ),
    path(
        "api/v1/webauthn/options/register/",
        views.WebAuthnRegisterOptionsView.as_view(),
        name="wa-options-register",
    ),
    path("api/v1/webauthn/register/", views.WebAuthnRegisterView.as_view(), name="wa-register"),
    path(
        "api/v1/webauthn/options/auth/",
        views.WebAuthnAuthOptionsView.as_view(),
        name="wa-options-auth",
    ),
    path("api/v1/webauthn/verify/", views.WebAuthnVerifyView.as_view(), name="wa-verify"),
    path(
        "api/v1/webauthn/<int:pk>/",
        views.PasskeyDetailView.as_view(),
        name="passkey-detail",
    ),
    path(
        "api/v1/.well-known/jwks.json",
        views.jwks_view,
        name="jwks",
    ),
    # RFC 8414 / OIDC convention puts JWKS at the ROOT .well-known. Generic
    # verifier libraries (jose, PyJWKClient, nginx auth modules) look here first,
    # so the root alias is what the SDKs actually consume; the /api/v1 path is
    # kept for backwards compatibility with anything already wired to it.
    path(".well-known/jwks.json", views.jwks_view, name="jwks-root"),
    path(
        ".well-known/passport-configuration",
        views.passport_configuration,
        name="passport-configuration",
    ),
    # Dev stub endpoints. The routes are always mounted, but DevLoginView's
    # _guard() returns 404 unless settings.ENABLE_DEV_LOGIN is True (defaults to
    # DEBUG), so a production build with DEBUG=False silently 404s. dev_status is
    # always readable — it only reports config, no secrets, no auth bypass.
    path("api/v1/dev/status/", dev_views.dev_status, name="dev-status"),
    path("api/v1/dev/login/", dev_views.DevLoginView.as_view(), name="dev-login"),
]

# 用户上传媒体（头像等）：开发期与生产都由 Django 直吐 /media/。
# 生产下 Nginx 在 passport.eacm.cn 反代 /media/，并挂载共享 media 卷做持久化；
# 前端（account.eacm.cn）经同源 /media 代理打到后端，同样走这里。
from django.views.static import serve as _static_serve

urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", _static_serve, {"document_root": settings.MEDIA_ROOT}),
]

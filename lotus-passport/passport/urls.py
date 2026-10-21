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
    # OAuth 授权确认页后端（§外部应用接入）：GET 取应用信息 / POST 消费票据并回跳。
    path(
        "api/v1/oauth/consent/",
        views.OAuthConsentView.as_view(),
        name="oauth-consent",
    ),
    # 授权码 + PKCE 换令牌（OAuth 2.1 风格，替代 fragment 下发）。
    path(
        "api/v1/oauth/token/",
        views.OAuthTokenExchangeView.as_view(),
        name="oauth-token-exchange",
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
    # Provider-agnostic generic login entry — same ordering caveat as above:
    # must precede the <provider> catch-all, else "login" would be parsed as
    # a provider name.
    path(
        "api/v1/oauth/login/",
        views.OAuthGenericLoginView.as_view(),
        name="oauth-generic-login",
    ),
    path(
        "api/v1/oauth/continue/",
        views.OAuthContinueView.as_view(),
        name="oauth-continue",
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
    # 密码找回（§9.4a reset）：邮件一次性 token；未配置 SMTP 时整体 503。
    path(
        "api/v1/security/password/reset-request/",
        views.PasswordResetRequestView.as_view(),
        name="password-reset-request",
    ),
    path(
        "api/v1/security/password/reset/",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    # 邮箱验证码（2026-08-27）：登录即注册 / 首次绑定 / 更改邮箱（双重验证）。
    path(
        "api/v1/security/email/send-code/",
        views.EmailCodeSendView.as_view(),
        name="email-send-code",
    ),
    path(
        "api/v1/login/email/",
        views.EmailLoginView.as_view(),
        name="email-login",
    ),
    path(
        "api/v1/security/email/bind/",
        views.EmailBindView.as_view(),
        name="email-bind",
    ),
    path(
        "api/v1/security/email/change/",
        views.EmailChangeView.as_view(),
        name="email-change",
    ),
    # Passkeys / WebAuthn (§9.4b) 已于 2026-08-27 砍除（端点整体移除，404）。
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

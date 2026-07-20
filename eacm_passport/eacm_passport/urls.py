"""
E时代ACM令牌 — 全局URL路由
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('django-admin-x7k9/', admin.site.urls),
    path('api/auth/', include('apps.oauth.urls')),
    path('api/user/', include('apps.users.urls')),
]
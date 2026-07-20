"""
OAuth认证URL路由
"""
from django.urls import path
from . import views

urlpatterns = [
    path('login/<str:provider>/', views.OAuthLoginView.as_view(), name='oauth-login'),
    path('callback/<str:provider>/', views.OAuthCallbackView.as_view(), name='oauth-callback'),
    path('refresh/', views.TokenRefreshView.as_view(), name='token-refresh'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
]
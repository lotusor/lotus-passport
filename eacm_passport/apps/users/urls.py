"""
用户相关URL路由
"""
from django.urls import path
from . import views

urlpatterns = [
    path('profile/', views.UserProfileView.as_view(), name='user-profile'),
    path('oauth-accounts/', views.OAuthAccountsView.as_view(), name='oauth-accounts'),
    path('oauth-accounts/<str:provider>/', views.OAuthAccountsView.as_view(), name='unbind-oauth'),
]
from django.contrib import admin
from .models import OAuthAccount


@admin.register(OAuthAccount)
class OAuthAccountAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'provider', 'provider_username', 'provider_user_id', 'bound_at')
    list_filter = ('provider',)
    search_fields = ('user__nickname', 'provider_username')
    readonly_fields = ('bound_at', 'access_token', 'refresh_token')
    exclude = ('access_token', 'refresh_token')
    ordering = ('-bound_at',)
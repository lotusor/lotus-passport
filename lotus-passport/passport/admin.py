from django.contrib import admin

from .models import OAuthAccount, PassportUser


@admin.register(PassportUser)
class PassportUserAdmin(admin.ModelAdmin):
    list_display = ("passport_id", "email", "nickname", "is_active", "created_at")
    search_fields = ("email", "nickname", "passport_id")
    readonly_fields = ("passport_id", "created_at", "updated_at")


@admin.register(OAuthAccount)
class OAuthAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "provider_user_id", "expires_at", "updated_at")
    list_filter = ("provider",)
    search_fields = ("provider_user_id", "user__email")
    readonly_fields = ("access_token_enc", "refresh_token_enc", "created_at", "updated_at")

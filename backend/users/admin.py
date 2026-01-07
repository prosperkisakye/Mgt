from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import (
    CustomUser,
    OneTimePassword,
    PermissionCategory,
    Permission,
    Role,
    RolePermission,
    UserPermission,
    UserRole,
    OTPModel,
)

# -----------------------------
# Custom User Admin
# -----------------------------
@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    model = CustomUser

    list_display = (
        "email",
        "fullname",
        "username",
        "user_type",
        "is_staff",
        "is_active",
        "is_email_verified",
        "created_at",
    )
    list_filter = (
        "user_type",
        "is_staff",
        "is_active",
        "is_email_verified",
        "gender",
    )
    search_fields = ("email", "fullname", "username")
    ordering = ("-created_at",)

    readonly_fields = ("last_login", "created_at", "updated_at", "session_id")

    fieldsets = (
        ("Basic Info", {
            "fields": ("email", "fullname", "username", "gender"),
        }),
        ("Status", {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "is_email_verified",
                "is_password_verified",
                "welcome_email_sent",
                "user_type",
            ),
        }),
        ("Security", {
            "fields": ("password", "session_id"),
        }),
        ("Permissions", {
            "fields": ("groups", "user_permissions"),
        }),
        ("Timestamps", {
            "fields": ("last_login", "created_at", "updated_at"),
        }),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "fullname",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )

    filter_horizontal = ("groups", "user_permissions")


# -----------------------------
# OTPs
# -----------------------------
@admin.register(OneTimePassword)
class OneTimePasswordAdmin(admin.ModelAdmin):
    list_display = ("purpose", "is_used", "expiry", "created_at")
    list_filter = ("is_used", "purpose")
    search_fields = ("purpose", "otp_hash")
    readonly_fields = ("created_at", "updated_at")


@admin.register(OTPModel)
class OTPModelAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "purpose",
        "is_used",
        "expires_at",
        "created_at",
    )
    list_filter = ("purpose", "is_used")
    search_fields = ("user__email", "value")
    readonly_fields = ("created_at",)


# -----------------------------
# Permissions & Roles
# -----------------------------
@admin.register(PermissionCategory)
class PermissionCategoryAdmin(admin.ModelAdmin):
    list_display = ("permission_category_name", "created_at")
    search_fields = ("permission_category_name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = (
        "permission_code",
        "permission_name",
        "category",
        "created_at",
    )
    list_filter = ("category",)
    search_fields = ("permission_code", "permission_name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission", "created_at")
    list_filter = ("role", "permission")
    search_fields = ("role__name", "permission__permission_name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("user__email", "role__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(UserPermission)
class UserPermissionAdmin(admin.ModelAdmin):
    list_display = ("user", "permission", "created_at")
    search_fields = ("user__email", "permission__permission_name")
    readonly_fields = ("created_at",)

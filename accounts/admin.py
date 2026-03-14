from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "role",
        "can_edit_content_label",
        "is_staff",
        "is_active",
        "is_superuser",
    )
    list_filter = ("role", "is_staff", "is_active", "is_superuser")
    list_editable = ("is_active", "is_staff")
    search_fields = ("username", "email", "first_name", "last_name", "faculty", "department")
    list_per_page = 30
    ordering = ("role", "last_name", "first_name")
    actions = (
        "make_staff",
        "make_teacher",
        "make_admin_role",
        "reset_staff_rights",
    )

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Персональные данные",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "email",
                    "faculty",
                    "department",
                )
            },
        ),
        (
            "Роль и права",
            {
                "fields": (
                    "role",
                )
            },
        ),
        (
            "Доступ в систему",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Важные даты",
            {
                "fields": ("last_login", "date_joined"),
                "classes": ("collapse",),
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2", "role"),
            },
        ),
    )

    filter_horizontal = ("groups", "user_permissions")
    raw_id_fields = ("groups", "user_permissions")

    @admin.display(description="Может преподавать")
    def can_edit_content_label(self, obj):
        return "Да" if obj.can_edit_content else "Нет"

    @admin.action(description="Сделать выбранных сотрудниками staff")
    def make_staff(self, request, queryset):
        queryset.update(is_staff=True)

    @admin.action(description="Снять staff у выбранных")
    def reset_staff_rights(self, request, queryset):
        queryset.update(is_staff=False)

    @admin.action(description="Сделать преподавателями")
    def make_teacher(self, request, queryset):
        queryset.update(role="teacher")

    @admin.action(description="Назначить роль admin")
    def make_admin_role(self, request, queryset):
        queryset.update(role="admin")

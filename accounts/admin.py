from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("ข้อมูลบริษัท", {
            "fields": ("employee_code",),
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("ข้อมูลบริษัท", {
            "fields": ("employee_code",),
        }),
    )

    list_display = UserAdmin.list_display + ("employee_code",)
    search_fields = UserAdmin.search_fields + ("employee_code",)
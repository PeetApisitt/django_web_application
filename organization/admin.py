from django.contrib import admin
from .models import Divisions

@admin.register(Divisions)
class DivisionsAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    search_fields = ("code", "name")
    list_filter = ("is_active",)
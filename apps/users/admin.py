from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.users.models import User


@admin.register(User)
class EmployeeAdmin(UserAdmin):
    list_display = ['id', 'username', 'email', 'company', 'is_staff', 'is_active']
    list_filter = ['company', 'is_staff', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    fieldsets = UserAdmin.fieldsets + (('Company', {'fields': ('company',)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Company', {'fields': ('email', 'company')}),
    )

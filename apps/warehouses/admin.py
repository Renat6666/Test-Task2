from django.contrib import admin

from apps.warehouses.models import Warehouse


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'company', 'manager', 'is_active']
    list_filter = ['company', 'is_active']
    search_fields = ['name', 'address']
    autocomplete_fields = ['manager']
    readonly_fields = ['created_at', 'updated_at']

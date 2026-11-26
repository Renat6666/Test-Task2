from django.contrib import admin

from apps.products.models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['id', 'sku', 'name', 'company', 'base_price', 'min_stock_level', 'is_deleted']
    list_filter = ['company', 'is_deleted']
    search_fields = ['sku', 'name']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at']

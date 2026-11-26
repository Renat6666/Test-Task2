from django.contrib import admin

from apps.transactions.models import InventoryEntry, InventoryTransaction


class InventoryEntryInline(admin.TabularInline):
    model = InventoryEntry
    extra = 0
    readonly_fields = ['warehouse', 'quantity_delta', 'created_at']
    can_delete = False


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'occurred_at',
        'transaction_type',
        'product',
        'quantity',
        'source_warehouse',
        'destination_warehouse',
        'created_by',
    ]
    list_filter = ['transaction_type', 'source_warehouse', 'destination_warehouse']
    search_fields = ['product__sku', 'product__name']
    date_hierarchy = 'occurred_at'
    inlines = [InventoryEntryInline]
    list_select_related = ['product', 'source_warehouse', 'destination_warehouse', 'created_by']

    def has_change_permission(self, request, obj=None):
        # The ledger is append only.
        return False

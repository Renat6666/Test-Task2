"""Transaction filters: by type, by warehouse and by date range."""

import django_filters
from django.db.models import Q

from apps.transactions.models import InventoryTransaction


class InventoryTransactionFilter(django_filters.FilterSet):
    transaction_type = django_filters.MultipleChoiceFilter(
        choices=InventoryTransaction.TransactionType.choices,
        help_text='Repeat the parameter to filter on several types.',
    )

    product = django_filters.NumberFilter(field_name='product_id')
    sku = django_filters.CharFilter(field_name='product__sku', lookup_expr='iexact')

    warehouse = django_filters.NumberFilter(
        method='filter_warehouse',
        label='Source or destination warehouse',
    )
    source_warehouse = django_filters.NumberFilter(field_name='source_warehouse_id')
    destination_warehouse = django_filters.NumberFilter(field_name='destination_warehouse_id')

    date_from = django_filters.IsoDateTimeFilter(field_name='occurred_at', lookup_expr='gte')
    date_to = django_filters.IsoDateTimeFilter(field_name='occurred_at', lookup_expr='lte')

    created_by = django_filters.NumberFilter(field_name='created_by_id')

    class Meta:
        model = InventoryTransaction
        fields = [
            'transaction_type',
            'product',
            'sku',
            'warehouse',
            'source_warehouse',
            'destination_warehouse',
            'date_from',
            'date_to',
            'created_by',
        ]

    def filter_warehouse(self, queryset, name, value):
        """Match transactions that touch the warehouse in either direction."""
        return queryset.filter(
            Q(source_warehouse_id=value) | Q(destination_warehouse_id=value)
        )

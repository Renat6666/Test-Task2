"""Product filters.

Free text search over name/SKU is handled by DRF's ``SearchFilter``
(``?search=``); this filter set covers the structured filters.
"""

import django_filters
from django.db.models import F

from apps.products.models import Product


class ProductFilter(django_filters.FilterSet):
    sku = django_filters.CharFilter(lookup_expr='iexact')
    name = django_filters.CharFilter(lookup_expr='icontains')

    min_price = django_filters.NumberFilter(field_name='base_price', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='base_price', lookup_expr='lte')

    min_stock = django_filters.NumberFilter(field_name='total_stock', lookup_expr='gte')
    max_stock = django_filters.NumberFilter(field_name='total_stock', lookup_expr='lte')

    low_stock = django_filters.BooleanFilter(
        method='filter_low_stock',
        label='Only products at or below their minimum stock level',
    )
    in_stock = django_filters.BooleanFilter(
        method='filter_in_stock',
        label='Only products with a positive stock',
    )
    include_deleted = django_filters.BooleanFilter(
        method='filter_include_deleted',
        label='Include soft deleted products',
    )

    class Meta:
        model = Product
        fields = ['sku', 'name', 'min_price', 'max_price', 'min_stock', 'max_stock']

    def filter_low_stock(self, queryset, name, value):
        if value is None:
            return queryset
        lookup = {'total_stock__lte' if value else 'total_stock__gt': F('min_stock_level')}
        return queryset.filter(**lookup)

    def filter_in_stock(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(total_stock__gt=0) if value else queryset.filter(total_stock__lte=0)

    def filter_include_deleted(self, queryset, name, value):
        # Handled by the view (it decides which selector to call); declared here
        # so django-filter does not reject the query parameter.
        return queryset

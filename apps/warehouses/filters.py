"""Warehouse filters."""

import django_filters

from apps.warehouses.models import Warehouse


class WarehouseFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    address = django_filters.CharFilter(lookup_expr='icontains')
    is_active = django_filters.BooleanFilter()
    manager = django_filters.NumberFilter(field_name='manager_id')

    class Meta:
        model = Warehouse
        fields = ['name', 'address', 'is_active', 'manager']

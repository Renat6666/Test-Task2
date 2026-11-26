"""Aggregations behind the reports.

All of them are plain Django ORM aggregates over the ledger; nothing is
pre-computed in the database.
"""

from decimal import Decimal

from django.db.models import ExpressionWrapper, F, Sum
from django.db.models.functions import Coalesce

from apps.common.fields import (
    VALUE_OUTPUT_FIELD,
    ZERO_QUANTITY,
    ZERO_VALUE,
    as_money,
    as_quantity,
)
from apps.products import selectors as product_selectors
from apps.transactions.models import InventoryEntry
from apps.warehouses import selectors as warehouse_selectors


def warehouse_value_rows(*, company) -> list[dict]:
    """Quantity and stock value held by each warehouse of a company."""
    warehouses = warehouse_selectors.warehouse_list_with_totals(company=company)
    return [
        {
            'warehouse_id': warehouse.pk,
            'name': warehouse.name,
            'address': warehouse.address,
            'is_active': warehouse.is_active,
            'total_quantity': as_quantity(warehouse.total_quantity),
            'total_value': as_money(warehouse.total_value),
        }
        for warehouse in warehouses.order_by('name')
    ]


def company_totals(*, company) -> dict:
    """Company wide quantity and stock value.

    Aggregated in a single query over the ledger entries instead of summing the
    per-warehouse rows in Python.
    """
    entry_value = ExpressionWrapper(
        F('quantity_delta') * F('transaction__product__base_price'),
        output_field=VALUE_OUTPUT_FIELD,
    )
    totals = InventoryEntry.objects.filter(
        warehouse__company=company,
        transaction__product__is_deleted=False,
    ).aggregate(
        total_quantity=Coalesce(Sum('quantity_delta'), ZERO_QUANTITY),
        total_value=Coalesce(Sum(entry_value), ZERO_VALUE),
    )
    return {
        'total_quantity': as_quantity(totals['total_quantity'] or Decimal('0')),
        'total_value': as_money(totals['total_value'] or Decimal('0')),
    }


def stock_rows(*, company) -> list[dict]:
    """Product level stock rows used by the stock report and its export."""
    return product_selectors.stock_report_rows(company=company)


def low_stock_rows(*, company):
    """Products at or below their minimum stock level."""
    return product_selectors.low_stock_products(company=company)

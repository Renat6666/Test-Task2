"""Read access to products, always with their calculated stock.

``total_stock`` and ``total_value`` are annotations computed from the
transaction ledger -- the database holds no stock column.
"""

from django.db.models import ExpressionWrapper, F, QuerySet

from apps.common.fields import VALUE_OUTPUT_FIELD, as_money, as_quantity
from apps.products.models import Product
from apps.transactions.selectors import stock_expression


def _annotate_stock(queryset: QuerySet[Product], *, warehouse_ids=None) -> QuerySet[Product]:
    """Add ``total_stock`` and ``total_value`` to a product queryset."""
    return queryset.annotate(
        total_stock=stock_expression(warehouse_ids=warehouse_ids),
    ).annotate(
        total_value=ExpressionWrapper(
            F('total_stock') * F('base_price'),
            output_field=VALUE_OUTPUT_FIELD,
        ),
    )


def product_list(*, company, include_deleted: bool = False, warehouse_ids=None) -> QuerySet[Product]:
    """Products of a company with their current stock and stock value.

    :param warehouse_ids: when given, the stock is calculated for those
        warehouses only (used by the warehouse detail endpoints).
    """
    queryset = Product.objects.filter(company=company).select_related('company')
    if not include_deleted:
        queryset = queryset.alive()
    return _annotate_stock(queryset, warehouse_ids=warehouse_ids)


def low_stock_products(*, company, warehouse_ids=None) -> QuerySet[Product]:
    """Products whose stock dropped to or below ``min_stock_level``."""
    return (
        product_list(company=company, warehouse_ids=warehouse_ids)
        .filter(total_stock__lte=F('min_stock_level'))
        .order_by('total_stock', 'name')
    )


def stock_report_rows(*, company) -> list[dict]:
    """Flat rows for the stock report / export.

    Returned as plain dicts (with the decimals quantised to a fixed precision)
    so the reporting layer -- pandas -- does not have to know about the ORM and
    the output does not depend on the database backend.
    """
    rows = (
        product_list(company=company)
        .values('id', 'sku', 'name', 'base_price', 'min_stock_level', 'total_stock', 'total_value')
        .order_by('sku')
    )
    return [
        {
            'product_id': row['id'],
            'sku': row['sku'],
            'name': row['name'],
            'base_price': as_money(row['base_price']),
            'min_stock_level': as_quantity(row['min_stock_level']),
            'total_stock': as_quantity(row['total_stock']),
            'total_value': as_money(row['total_value']),
            'is_low_stock': row['total_stock'] <= row['min_stock_level'],
        }
        for row in rows
    ]

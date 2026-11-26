"""Read access to the ledger, and the stock expressions built on top of it.

Balances are **never** stored. Everything below derives the current stock from
``SUM(inventory_entries.quantity_delta)`` using Django ORM expressions, so a
balance cannot drift away from the transaction history.
"""

from decimal import Decimal

from django.db.models import OuterRef, Q, QuerySet, Subquery, Sum
from django.db.models.functions import Coalesce

from apps.common.fields import QUANTITY_OUTPUT_FIELD, ZERO_QUANTITY, as_quantity
from apps.transactions.models import InventoryEntry, InventoryTransaction


def stock_expression(*, product_ref: str = 'pk', warehouse_ids=None):
    """Return an expression with the stock of the *outer* product row.

    Correlated subquery rather than a ``JOIN`` + ``GROUP BY`` on purpose: it
    composes with any other annotation (and with pagination) without the row
    multiplication a second join would introduce.

    :param product_ref: name of the outer field holding the product id.
    :param warehouse_ids: restrict the balance to these warehouses; ``None``
        means "every warehouse of the company" (i.e. the total stock).
    """
    entries = InventoryEntry.objects.filter(
        transaction__product=OuterRef(product_ref)
    )
    if warehouse_ids is not None:
        entries = entries.filter(warehouse_id__in=list(warehouse_ids))

    balance = (
        entries.order_by()
        .values('transaction__product')
        .annotate(total=Sum('quantity_delta'))
        .values('total')[:1]
    )
    return Coalesce(
        Subquery(balance, output_field=QUANTITY_OUTPUT_FIELD),
        ZERO_QUANTITY,
        output_field=QUANTITY_OUTPUT_FIELD,
    )


def product_stock(*, product, warehouse=None) -> Decimal:
    """Current stock of one product, optionally on a single warehouse.

    The result is quantised so the value does not depend on how the database
    backend happens to render a ``SUM`` over a numeric column.
    """
    entries = InventoryEntry.objects.filter(transaction__product=product)
    if warehouse is not None:
        entries = entries.filter(warehouse=warehouse)

    total = entries.aggregate(
        total=Coalesce(Sum('quantity_delta'), ZERO_QUANTITY)
    )['total']
    return as_quantity(total or Decimal('0'))


def stock_per_warehouse(*, product) -> QuerySet:
    """Per-warehouse breakdown of a product's stock.

    Yields dicts of ``warehouse_id``, ``warehouse_name`` and ``quantity``.
    """
    return (
        InventoryEntry.objects.filter(transaction__product=product)
        .values('warehouse_id', 'warehouse__name')
        .annotate(quantity=Sum('quantity_delta'))
        .filter(~Q(quantity=0))
        .order_by('warehouse__name')
    )


def transaction_list(*, company) -> QuerySet[InventoryTransaction]:
    """Transactions of a company, ready to be serialized."""
    return (
        InventoryTransaction.objects.filter(product__company=company)
        .select_related(
            'product',
            'source_warehouse',
            'destination_warehouse',
            'created_by',
        )
    )

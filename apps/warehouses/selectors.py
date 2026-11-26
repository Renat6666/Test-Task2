"""Read access to warehouses and their calculated totals."""

from django.db.models import ExpressionWrapper, F, Q, QuerySet, Sum
from django.db.models.functions import Coalesce

from apps.common.fields import (
    QUANTITY_OUTPUT_FIELD,
    VALUE_OUTPUT_FIELD,
    ZERO_QUANTITY,
    ZERO_VALUE,
)
from apps.warehouses.models import Warehouse

#: Soft deleted products do not count towards the stock of a warehouse.
_LIVE_PRODUCT = Q(inventory_entries__transaction__product__is_deleted=False)

#: quantity_delta * base_price of a single ledger entry.
_ENTRY_VALUE = ExpressionWrapper(
    F('inventory_entries__quantity_delta')
    * F('inventory_entries__transaction__product__base_price'),
    output_field=VALUE_OUTPUT_FIELD,
)


def warehouse_list(*, company) -> QuerySet[Warehouse]:
    """Warehouses of a company."""
    return Warehouse.objects.filter(company=company).select_related('manager')


def warehouse_list_with_totals(*, company) -> QuerySet[Warehouse]:
    """Warehouses annotated with the quantity and the value they hold.

    Both numbers come straight from the ledger; warehouses without any
    movement are kept (with zeros) thanks to ``Coalesce``.
    """
    return warehouse_list(company=company).annotate(
        total_quantity=Coalesce(
            Sum('inventory_entries__quantity_delta', filter=_LIVE_PRODUCT),
            ZERO_QUANTITY,
            output_field=QUANTITY_OUTPUT_FIELD,
        ),
        total_value=Coalesce(
            Sum(_ENTRY_VALUE, filter=_LIVE_PRODUCT),
            ZERO_VALUE,
            output_field=VALUE_OUTPUT_FIELD,
        ),
    )


def has_movements(*, warehouse) -> bool:
    """Whether any stock ever moved in or out of this warehouse."""
    return warehouse.inventory_entries.exists()

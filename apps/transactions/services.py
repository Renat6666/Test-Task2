"""Stock movement services.

This module owns every business rule about moving stock. The rules are enforced
at three levels:

1. serializers reject structurally invalid payloads,
2. the functions below reject rule violations (ownership, insufficient stock),
3. database check constraints are the last line of defence.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.common.cache import invalidate_company_reports
from apps.common.exceptions import BusinessRuleViolation, InsufficientStock
from apps.products.models import Product
from apps.transactions import notifications, selectors
from apps.transactions.models import InventoryEntry, InventoryTransaction

logger = logging.getLogger(__name__)

TransactionType = InventoryTransaction.TransactionType

#: Which warehouse each transaction type requires.
WAREHOUSE_REQUIREMENTS = {
    TransactionType.IN: {'source': False, 'destination': True},
    TransactionType.OUT: {'source': True, 'destination': False},
    TransactionType.TRANSFER: {'source': True, 'destination': True},
}


def validate_warehouse_combination(
    *, transaction_type: str, source_warehouse, destination_warehouse
) -> None:
    """Check the warehouses against the transaction type.

    ``IN`` needs a destination only, ``OUT`` a source only and ``TRANSFER``
    both (and they must differ).
    """
    requirements = WAREHOUSE_REQUIREMENTS[transaction_type]
    errors = {}

    if requirements['source'] and source_warehouse is None:
        errors['source_warehouse'] = [f'Required for {transaction_type} transactions.']
    if not requirements['source'] and source_warehouse is not None:
        errors['source_warehouse'] = [f'Must be empty for {transaction_type} transactions.']

    if requirements['destination'] and destination_warehouse is None:
        errors['destination_warehouse'] = [f'Required for {transaction_type} transactions.']
    if not requirements['destination'] and destination_warehouse is not None:
        errors['destination_warehouse'] = [f'Must be empty for {transaction_type} transactions.']

    if (
        not errors
        and transaction_type == TransactionType.TRANSFER
        and source_warehouse.pk == destination_warehouse.pk
    ):
        errors['destination_warehouse'] = ['A transfer needs two different warehouses.']

    if errors:
        raise BusinessRuleViolation(errors)


def _assert_belongs_to_company(*, company, product, warehouses) -> None:
    """Reject objects belonging to another company (defence in depth)."""
    if product.company_id != company.pk:
        raise BusinessRuleViolation({'product': ['Unknown product.']})
    if product.is_deleted:
        raise BusinessRuleViolation({'product': ['This product has been deleted.']})

    for field, warehouse in warehouses.items():
        if warehouse is None:
            continue
        if warehouse.company_id != company.pk:
            raise BusinessRuleViolation({field: ['Unknown warehouse.']})
        if not warehouse.is_active:
            raise BusinessRuleViolation({field: ['This warehouse is not active.']})


@transaction.atomic
def create_inventory_transaction(
    *,
    company,
    created_by,
    product: Product,
    transaction_type: str,
    quantity: Decimal,
    source_warehouse=None,
    destination_warehouse=None,
    occurred_at=None,
) -> InventoryTransaction:
    """Record a stock movement and its ledger entries.

    Outgoing movements are refused when the source warehouse does not hold
    enough stock. The product row is locked for the duration of the
    transaction, so two concurrent shipments of the same article cannot both
    pass the stock check and overdraw the warehouse.
    """
    _assert_belongs_to_company(
        company=company,
        product=product,
        warehouses={
            'source_warehouse': source_warehouse,
            'destination_warehouse': destination_warehouse,
        },
    )
    validate_warehouse_combination(
        transaction_type=transaction_type,
        source_warehouse=source_warehouse,
        destination_warehouse=destination_warehouse,
    )

    if quantity <= 0:
        raise BusinessRuleViolation({'quantity': ['Must be greater than zero.']})

    # Serialise concurrent movements of this article.
    product = Product.objects.select_for_update().get(pk=product.pk)

    if source_warehouse is not None:
        available = selectors.product_stock(product=product, warehouse=source_warehouse)
        if available < quantity:
            raise InsufficientStock(
                product=product,
                warehouse=source_warehouse,
                requested=quantity,
                available=available,
            )

    inventory_transaction = InventoryTransaction.objects.create(
        product=product,
        transaction_type=transaction_type,
        quantity=quantity,
        source_warehouse=source_warehouse,
        destination_warehouse=destination_warehouse,
        occurred_at=occurred_at or timezone.now(),
        created_by=created_by,
    )

    entries = []
    if source_warehouse is not None:
        entries.append(
            InventoryEntry(
                transaction=inventory_transaction,
                warehouse=source_warehouse,
                quantity_delta=-quantity,
            )
        )
    if destination_warehouse is not None:
        entries.append(
            InventoryEntry(
                transaction=inventory_transaction,
                warehouse=destination_warehouse,
                quantity_delta=quantity,
            )
        )
    InventoryEntry.objects.bulk_create(entries)

    # The cached warehouse value report is now stale.
    transaction.on_commit(lambda: invalidate_company_reports(company.pk))

    if transaction_type == TransactionType.OUT:
        remaining = selectors.product_stock(product=product, warehouse=source_warehouse)
        if remaining < product.min_stock_level:
            transaction.on_commit(
                lambda: notifications.send_low_stock_alert(
                    product=product,
                    warehouse=source_warehouse,
                    remaining=remaining,
                )
            )

    logger.info(
        'Recorded %s of %s x %s (transaction #%s)',
        transaction_type, quantity, product.sku, inventory_transaction.pk,
    )
    return inventory_transaction

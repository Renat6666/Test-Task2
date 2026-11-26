from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class InventoryTransaction(models.Model):
    """A single stock movement recorded by an employee.

    A transaction is the *intent* ("move 10 pieces from A to B"); the signed
    per-warehouse effect of it lives in :class:`InventoryEntry`. Keeping the two
    apart means a balance is always ``SUM(quantity_delta)`` over the entries,
    whatever the transaction type was -- no stored balance anywhere.

    Transactions are append only: there is no API to edit or delete them, which
    keeps the ledger (and therefore every balance) reproducible.
    """

    class TransactionType(models.TextChoices):
        IN = 'IN', 'Incoming'
        OUT = 'OUT', 'Outgoing'
        TRANSFER = 'TRANSFER', 'Transfer'

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.PROTECT,
        related_name='transactions',
    )

    transaction_type = models.CharField(
        max_length=10,
        choices=TransactionType.choices,
    )

    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
    )

    source_warehouse = models.ForeignKey(
        'warehouses.Warehouse',
        on_delete=models.PROTECT,
        related_name='outgoing_transactions',
        null=True,
        blank=True,
    )

    destination_warehouse = models.ForeignKey(
        'warehouses.Warehouse',
        on_delete=models.PROTECT,
        related_name='incoming_transactions',
        null=True,
        blank=True,
    )

    occurred_at = models.DateTimeField(default=timezone.now)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='inventory_transactions',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_transactions'
        ordering = ['-occurred_at', '-id']

        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name='transaction_quantity_positive',
            ),

            # IN needs a destination, OUT needs a source, TRANSFER needs both
            # and the two warehouses must differ.
            models.CheckConstraint(
                condition=(
                    Q(
                        transaction_type='IN',
                        source_warehouse__isnull=True,
                        destination_warehouse__isnull=False,
                    )
                    |
                    Q(
                        transaction_type='OUT',
                        source_warehouse__isnull=False,
                        destination_warehouse__isnull=True,
                    )
                    |
                    (
                        Q(
                            transaction_type='TRANSFER',
                            source_warehouse__isnull=False,
                            destination_warehouse__isnull=False,
                        )
                        & ~Q(
                            source_warehouse=F('destination_warehouse')
                        )
                    )
                ),
                name='transaction_warehouse_validation',
            ),
        ]

        indexes = [
            models.Index(
                fields=['product', '-occurred_at'],
                name='tx_product_occurred_idx',
            ),
            models.Index(
                fields=['transaction_type', '-occurred_at'],
                name='tx_type_occurred_idx',
            ),
        ]

    def __str__(self):
        return f'{self.transaction_type}: {self.product}'


class InventoryEntry(models.Model):
    """The signed effect of a transaction on one warehouse.

    ``IN`` creates one ``+quantity`` entry, ``OUT`` one ``-quantity`` entry and
    ``TRANSFER`` a pair (``-quantity`` on the source, ``+quantity`` on the
    destination), so a transfer nets out to zero company wide.
    """

    transaction = models.ForeignKey(
        InventoryTransaction,
        on_delete=models.PROTECT,
        related_name='entries',
    )

    warehouse = models.ForeignKey(
        'warehouses.Warehouse',
        on_delete=models.PROTECT,
        related_name='inventory_entries',
    )

    quantity_delta = models.DecimalField(
        max_digits=14,
        decimal_places=3,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_entries'

        constraints = [
            models.CheckConstraint(
                condition=~Q(quantity_delta=0),
                name='inventory_entry_non_zero',
            ),
            models.UniqueConstraint(
                fields=['transaction', 'warehouse'],
                name='unique_warehouse_per_transaction',
            ),
        ]

        indexes = [
            models.Index(
                fields=['warehouse', 'transaction'],
                name='entry_warehouse_tx_idx',
            ),
        ]

    def __str__(self):
        return f'{self.warehouse}: {self.quantity_delta:+}'

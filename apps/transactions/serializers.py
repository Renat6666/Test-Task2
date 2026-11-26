from decimal import Decimal

from rest_framework import serializers

from apps.common.fields import QUANTITY_DECIMAL_PLACES, QUANTITY_MAX_DIGITS
from apps.common.serializers import WriteSerializer
from apps.products.models import Product
from apps.transactions.models import InventoryEntry, InventoryTransaction
from apps.warehouses.models import Warehouse


class ProductBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ['id', 'sku', 'name']


class WarehouseBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ['id', 'name']


class InventoryEntrySerializer(serializers.ModelSerializer):
    """The signed effect of the transaction on one warehouse."""

    warehouse = WarehouseBriefSerializer(read_only=True)

    class Meta:
        model = InventoryEntry
        fields = ['id', 'warehouse', 'quantity_delta']


class InventoryTransactionSerializer(serializers.ModelSerializer):
    product = ProductBriefSerializer(read_only=True)
    source_warehouse = WarehouseBriefSerializer(read_only=True)
    destination_warehouse = WarehouseBriefSerializer(read_only=True)
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = InventoryTransaction
        fields = [
            'id',
            'product',
            'transaction_type',
            'quantity',
            'source_warehouse',
            'destination_warehouse',
            'occurred_at',
            'created_by',
            'created_at',
        ]
        read_only_fields = fields

    def get_created_by(self, inventory_transaction) -> str | None:
        user = inventory_transaction.created_by
        return user.get_username() if user else None


class InventoryTransactionDetailSerializer(InventoryTransactionSerializer):
    entries = InventoryEntrySerializer(many=True, read_only=True)

    class Meta(InventoryTransactionSerializer.Meta):
        fields = InventoryTransactionSerializer.Meta.fields + ['entries']
        read_only_fields = fields


class InventoryTransactionCreateSerializer(WriteSerializer):
    """Validates a stock movement payload.

    The related object querysets are narrowed to the company of the requesting
    employee, so another company's ids simply do not exist here.
    """

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.none())
    transaction_type = serializers.ChoiceField(
        choices=InventoryTransaction.TransactionType.choices
    )
    quantity = serializers.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        min_value=Decimal('0.001'),
    )
    source_warehouse = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.none(), required=False, allow_null=True, default=None
    )
    destination_warehouse = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.none(), required=False, allow_null=True, default=None
    )
    occurred_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        default=None,
        help_text='Defaults to now.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        company = self.context.get('company')
        if company is None:
            return
        self.fields['product'].queryset = Product.objects.alive().filter(company=company)
        warehouses = Warehouse.objects.filter(company=company, is_active=True)
        self.fields['source_warehouse'].queryset = warehouses
        self.fields['destination_warehouse'].queryset = warehouses

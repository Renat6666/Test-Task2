from decimal import Decimal

from rest_framework import serializers

from apps.common.fields import (
    MONEY_DECIMAL_PLACES,
    MONEY_MAX_DIGITS,
    QUANTITY_DECIMAL_PLACES,
    QUANTITY_MAX_DIGITS,
    VALUE_MAX_DIGITS,
)
from apps.common.serializers import WriteSerializer
from apps.products.models import Product


class ProductSerializer(serializers.ModelSerializer):
    """Read representation including the calculated stock figures."""

    total_stock = serializers.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        read_only=True,
        help_text='Current stock, derived from the transaction ledger.',
    )
    total_value = serializers.DecimalField(
        max_digits=VALUE_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
        read_only=True,
        help_text='total_stock * base_price',
    )
    is_low_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id',
            'sku',
            'name',
            'description',
            'base_price',
            'min_stock_level',
            'total_stock',
            'total_value',
            'is_low_stock',
            'is_deleted',
            'deleted_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_is_low_stock(self, product) -> bool:
        total_stock = getattr(product, 'total_stock', None)
        if total_stock is None:
            return False
        return Decimal(total_stock) <= product.min_stock_level


class ProductWriteSerializer(WriteSerializer):
    """Validates the product payload; the service performs the write."""

    sku = serializers.CharField(max_length=100)
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(
        max_length=5000, required=False, allow_blank=True, default=''
    )
    base_price = serializers.DecimalField(
        max_digits=MONEY_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
        min_value=Decimal('0'),
    )
    min_stock_level = serializers.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        min_value=Decimal('0'),
        required=False,
        default=Decimal('0'),
    )


class WarehouseStockSerializer(serializers.Serializer):
    """Stock of one product, broken down per warehouse."""

    warehouse_id = serializers.IntegerField()
    warehouse_name = serializers.CharField(source='warehouse__name')
    quantity = serializers.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS, decimal_places=QUANTITY_DECIMAL_PLACES
    )

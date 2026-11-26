from rest_framework import serializers

from apps.common.fields import (
    MONEY_DECIMAL_PLACES,
    MONEY_MAX_DIGITS,
    QUANTITY_DECIMAL_PLACES,
    QUANTITY_MAX_DIGITS,
    VALUE_MAX_DIGITS,
)


class StockRowSerializer(serializers.Serializer):
    """One line of the stock report."""

    product_id = serializers.IntegerField()
    sku = serializers.CharField()
    name = serializers.CharField()
    base_price = serializers.DecimalField(
        max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES
    )
    min_stock_level = serializers.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS, decimal_places=QUANTITY_DECIMAL_PLACES
    )
    total_stock = serializers.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS, decimal_places=QUANTITY_DECIMAL_PLACES
    )
    total_value = serializers.DecimalField(
        max_digits=VALUE_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES
    )
    is_low_stock = serializers.BooleanField()


# The warehouse value report is built as a plain payload (it is cached in Redis
# as primitives). These serializers exist to describe that payload in the
# OpenAPI schema; the view does not serialize through them.

class ReportCompanySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class WarehouseValueRowSerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    is_active = serializers.BooleanField()
    total_quantity = serializers.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS, decimal_places=QUANTITY_DECIMAL_PLACES
    )
    total_value = serializers.DecimalField(
        max_digits=VALUE_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES
    )


class WarehouseValueReportSerializer(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    company = ReportCompanySerializer()
    total_quantity = serializers.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS, decimal_places=QUANTITY_DECIMAL_PLACES
    )
    total_value = serializers.DecimalField(
        max_digits=VALUE_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES
    )
    warehouses = WarehouseValueRowSerializer(many=True)
    cached = serializers.BooleanField(
        help_text='Whether this answer came from Redis instead of being recomputed.'
    )

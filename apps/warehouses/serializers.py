from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.common.fields import (
    MONEY_DECIMAL_PLACES,
    QUANTITY_DECIMAL_PLACES,
    QUANTITY_MAX_DIGITS,
    VALUE_MAX_DIGITS,
)
from apps.common.serializers import WriteSerializer
from apps.warehouses.models import Warehouse

User = get_user_model()


class WarehouseSerializer(serializers.ModelSerializer):
    """Read representation with the calculated totals."""

    manager_username = serializers.SerializerMethodField()

    total_quantity = serializers.DecimalField(
        max_digits=QUANTITY_MAX_DIGITS,
        decimal_places=QUANTITY_DECIMAL_PLACES,
        read_only=True,
        required=False,
    )
    total_value = serializers.DecimalField(
        max_digits=VALUE_MAX_DIGITS,
        decimal_places=MONEY_DECIMAL_PLACES,
        read_only=True,
        required=False,
    )

    class Meta:
        model = Warehouse
        fields = [
            'id',
            'name',
            'address',
            'manager',
            'manager_username',
            'is_active',
            'total_quantity',
            'total_value',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_manager_username(self, warehouse) -> str | None:
        return warehouse.manager.username if warehouse.manager_id else None


class WarehouseWriteSerializer(WriteSerializer):
    name = serializers.CharField(max_length=255)
    address = serializers.CharField(max_length=500)
    manager = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.none(),
        required=False,
        allow_null=True,
        default=None,
        help_text='Employee that receives the low stock alerts of this warehouse.',
    )
    is_active = serializers.BooleanField(required=False, default=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only colleagues can be picked as a manager.
        company = self.context.get('company')
        if company is not None:
            self.fields['manager'].queryset = User.objects.filter(company=company)

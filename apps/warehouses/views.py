from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.decorators import action

from apps.common.viewsets import ServiceModelViewSet
from apps.products import selectors as product_selectors
from apps.products.serializers import ProductSerializer
from apps.warehouses import selectors, services
from apps.warehouses.filters import WarehouseFilter
from apps.warehouses.models import Warehouse
from apps.warehouses.serializers import WarehouseSerializer, WarehouseWriteSerializer


@extend_schema_view(
    list=extend_schema(
        summary='List warehouses',
        description=(
            'Each warehouse comes with the `total_quantity` and `total_value` '
            'it currently holds, calculated from the transaction ledger.'
        ),
    ),
    create=extend_schema(summary='Create a warehouse'),
    retrieve=extend_schema(summary='Get a warehouse'),
    update=extend_schema(summary='Replace a warehouse'),
    partial_update=extend_schema(summary='Update a warehouse'),
    destroy=extend_schema(
        summary='Delete an unused warehouse',
        description=(
            'Only possible while the warehouse has no stock movements -- '
            'deleting one that appears in the ledger would rewrite history. '
            'Retire it with `PATCH {"is_active": false}` instead.'
        ),
        responses={
            204: OpenApiResponse(description='Deleted'),
            409: OpenApiResponse(description='The warehouse has stock movements'),
        },
    ),
)
@extend_schema(tags=['warehouses'])
class WarehouseViewSet(ServiceModelViewSet):
    """CRUD for warehouses.

    Each warehouse is returned with the quantity and the stock value it
    currently holds, both calculated from the transaction ledger.
    """

    queryset = Warehouse.objects.none()  # schema generation only; see CompanyScopedQuerysetMixin
    read_serializer_class = WarehouseSerializer
    write_serializer_class = WarehouseWriteSerializer
    filterset_class = WarehouseFilter
    search_fields = ['name', 'address']
    ordering_fields = ['name', 'total_quantity', 'total_value', 'created_at']
    ordering = ['name']

    def get_company_queryset(self):
        return selectors.warehouse_list_with_totals(company=self.company)

    # Writes -> services ----------------------------------------------------

    def create_object(self, validated_data):
        return services.create_warehouse(company=self.company, **validated_data)

    def update_object(self, instance, validated_data):
        return services.update_warehouse(warehouse=instance, **validated_data)

    def delete_object(self, instance):
        services.delete_warehouse(warehouse=instance)

    # Extra routes ----------------------------------------------------------

    @extend_schema(
        summary='Products stored on this warehouse',
        description=(
            'Products with a non-zero balance here. `total_stock` and '
            '`total_value` are scoped to this warehouse only, not company wide.'
        ),
        responses={200: ProductSerializer(many=True)},
    )
    @action(detail=True, methods=['get'])
    def stock(self, request, pk=None):
        """Products stored on this warehouse with their stock and value.

        The balances are scoped to this warehouse only.
        """
        warehouse = self.get_object()
        products = product_selectors.product_list(
            company=self.company, warehouse_ids=[warehouse.pk]
        ).exclude(total_stock=0).order_by('name')

        page = self.paginate_queryset(products)
        serializer = ProductSerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)

    @extend_schema(
        summary='Products running out on this warehouse',
        description=(
            'Products whose balance *on this warehouse* is at or below their '
            '`min_stock_level`.'
        ),
        responses={200: ProductSerializer(many=True)},
    )
    @action(detail=True, methods=['get'], url_path='low-stock')
    def low_stock(self, request, pk=None):
        """Products on this warehouse at or below their minimum stock level."""
        warehouse = self.get_object()
        products = product_selectors.low_stock_products(
            company=self.company, warehouse_ids=[warehouse.pk]
        )

        page = self.paginate_queryset(products)
        serializer = ProductSerializer(page, many=True, context=self.get_serializer_context())
        return self.get_paginated_response(serializer.data)

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.common.viewsets import ServiceModelViewSet
from apps.products import selectors, services
from apps.products.filters import ProductFilter
from apps.products.models import Product
from apps.products.serializers import (
    ProductSerializer,
    ProductWriteSerializer,
    WarehouseStockSerializer,
)
from apps.transactions import selectors as transaction_selectors


@extend_schema_view(
    list=extend_schema(
        summary='List products',
        description=(
            'Every row carries its `total_stock` and `total_value`, calculated '
            'from the transaction ledger. Searchable by name or SKU '
            '(`?search=`), filterable, and sortable by stock or price '
            '(`?ordering=-total_stock`).'
        ),
    ),
    create=extend_schema(summary='Create a product'),
    retrieve=extend_schema(
        summary='Get a product',
        description=(
            'Soft deleted products stay reachable here, so the transaction '
            'history keeps resolving.'
        ),
    ),
    update=extend_schema(summary='Replace a product'),
    partial_update=extend_schema(summary='Update a product'),
    destroy=extend_schema(
        summary='Soft delete a product',
        description=(
            'Marks the product deleted instead of removing the row, so past '
            'shipments keep resolving. It leaves the catalogue and both '
            'reports but stays reachable at its detail URL, and its SKU '
            'becomes free for reuse.'
        ),
    ),
)
@extend_schema(tags=['products'])
class ProductViewSet(ServiceModelViewSet):
    """CRUD for products.

    Every row carries its calculated ``total_stock`` / ``total_value``, so the
    list can be searched (``?search=``), filtered and sorted by stock or price.
    ``DELETE`` is a soft delete.
    """

    queryset = Product.objects.none()  # schema generation only; see CompanyScopedQuerysetMixin
    read_serializer_class = ProductSerializer
    write_serializer_class = ProductWriteSerializer
    filterset_class = ProductFilter
    search_fields = ['name', 'sku']
    ordering_fields = ['name', 'sku', 'base_price', 'total_stock', 'total_value', 'created_at']
    ordering = ['name']

    def get_company_queryset(self):
        # ``include_deleted`` is only honoured on the list endpoint; detail
        # routes always resolve soft deleted products so the history stays
        # navigable.
        include_deleted = self.action != 'list' or self._include_deleted_requested()
        return selectors.product_list(company=self.company, include_deleted=include_deleted)

    def _include_deleted_requested(self) -> bool:
        return self.request.query_params.get('include_deleted', '').lower() in {
            '1', 'true', 'yes',
        }

    # Writes -> services ----------------------------------------------------

    def create_object(self, validated_data):
        return services.create_product(company=self.company, **validated_data)

    def update_object(self, instance, validated_data):
        return services.update_product(product=instance, **validated_data)

    def delete_object(self, instance):
        services.soft_delete_product(product=instance)

    # Extra routes ----------------------------------------------------------

    @extend_schema(
        summary='Restore a soft deleted product',
        request=None,
        responses={
            200: ProductSerializer,
            400: OpenApiResponse(description='The SKU has been taken by another product'),
        },
    )
    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        """Undo a soft delete."""
        product = services.restore_product(product=self.get_object())
        return Response(self.get_read_serializer(self.reload(product)).data)

    @extend_schema(
        summary='Stock of this product per warehouse',
        description='Warehouses holding a non-zero balance of this product.',
        responses={200: WarehouseStockSerializer(many=True)},
    )
    @action(detail=True, methods=['get'])
    def stock(self, request, pk=None):
        """Per-warehouse breakdown of this product's stock."""
        rows = transaction_selectors.stock_per_warehouse(product=self.get_object())
        return Response(WarehouseStockSerializer(rows, many=True).data)

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import mixins, viewsets

from apps.common.viewsets import CompanyScopedQuerysetMixin, ReadWriteSerializerMixin
from apps.transactions import selectors, services
from apps.transactions.filters import InventoryTransactionFilter
from apps.transactions.models import InventoryTransaction
from apps.transactions.serializers import (
    InventoryTransactionCreateSerializer,
    InventoryTransactionDetailSerializer,
    InventoryTransactionSerializer,
)
from apps.transactions.throttles import TransactionCreateThrottle


@extend_schema_view(
    list=extend_schema(
        summary='List stock movements',
        description=(
            'Filterable by type, by warehouse (source or destination), by '
            'product/SKU and by date range; newest first by default.'
        ),
    ),
    retrieve=extend_schema(
        summary='Get a stock movement',
        description=(
            'Includes the ledger `entries`: the signed effect of the movement '
            'on each warehouse.'
        ),
    ),
    create=extend_schema(
        summary='Record a stock movement',
        description=(
            'Records an `IN`, `OUT` or `TRANSFER` together with its ledger '
            'entries.\n\n'
            '**Required warehouses per type**\n'
            '| Type | source_warehouse | destination_warehouse |\n'
            '| --- | --- | --- |\n'
            '| `IN` | must be empty | required |\n'
            '| `OUT` | required | must be empty |\n'
            '| `TRANSFER` | required | required (and different) |\n\n'
            'An `OUT` or `TRANSFER` is refused when the source warehouse does '
            'not hold enough stock; the error body then also carries '
            '`available_quantity`.\n\n'
            'Limited to 50 requests per employee per minute.'
        ),
        responses={
            201: InventoryTransactionSerializer,
            400: OpenApiResponse(
                description=(
                    'Insufficient stock, wrong warehouse combination, unknown '
                    'product, or a deleted product / inactive warehouse'
                )
            ),
            429: OpenApiResponse(description='Rate limit exceeded (50/min per employee)'),
        },
    ),
)
@extend_schema(tags=['transactions'])
class InventoryTransactionViewSet(
    ReadWriteSerializerMixin,
    CompanyScopedQuerysetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Stock movements: ``IN``, ``OUT`` and ``TRANSFER``.

    The ledger is append only -- there is deliberately no ``PUT``/``DELETE``,
    because every balance in the system is derived from these rows.

    Creating a transaction is rate limited to 50 per employee per minute
    (counters in Redis).
    """

    queryset = InventoryTransaction.objects.none()  # schema generation only
    read_serializer_class = InventoryTransactionSerializer
    write_serializer_class = InventoryTransactionCreateSerializer
    write_actions = ('create',)

    filterset_class = InventoryTransactionFilter
    search_fields = ['product__name', 'product__sku']
    ordering_fields = ['occurred_at', 'created_at', 'quantity']
    ordering = ['-occurred_at', '-id']

    def get_company_queryset(self):
        return selectors.transaction_list(company=self.company)

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return InventoryTransactionDetailSerializer
        return super().get_serializer_class()

    def get_throttles(self):
        if self.action == 'create':
            return [TransactionCreateThrottle()]
        return super().get_throttles()

    def perform_create(self, serializer):
        serializer.instance = services.create_inventory_transaction(
            company=self.company,
            created_by=self.request.user,
            **serializer.validated_data,
        )

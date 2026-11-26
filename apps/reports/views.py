from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.common.viewsets import CompanyScopedMixin
from apps.products.serializers import ProductSerializer
from apps.reports import exports, selectors, services
from apps.reports.serializers import (
    StockRowSerializer,
    WarehouseValueReportSerializer,
)


@extend_schema(tags=['reports'])
class ReportViewSet(CompanyScopedMixin, viewsets.ViewSet):
    """Read-only reporting endpoints."""

    def get_serializer_context(self):
        return {'request': self.request, 'view': self, 'company': self.company}

    @extend_schema(
        summary='Total stock value per warehouse (cached)',
        description=(
            'Aggregates the whole transaction ledger into the quantity and the '
            'stock value each warehouse holds, plus the company totals.\n\n'
            'Because the query is expensive the payload is cached in Redis. The '
            'entry is invalidated as soon as stock moves, a price changes or a '
            'product is soft deleted, so a stale number is never served. '
            '`cached` tells you which of the two happened.'
        ),
        parameters=[
            OpenApiParameter(
                name='refresh',
                type=OpenApiTypes.BOOL,
                description='Recompute and overwrite the cached entry.',
            ),
        ],
        responses={200: WarehouseValueReportSerializer},
    )
    @action(detail=False, methods=['get'], url_path='warehouse-value')
    def warehouse_value(self, request):
        refresh = request.query_params.get('refresh', '').lower() in {'1', 'true', 'yes'}
        payload, from_cache = services.warehouse_value_report(
            company=self.company, refresh=refresh
        )
        return Response({**payload, 'cached': from_cache})

    @extend_schema(
        summary='Current stock of every product',
        description=(
            'One row per live product with its calculated stock, stock value '
            'and whether it sits at or below `min_stock_level`. Not paginated '
            '-- it is the report the export is built from.'
        ),
        responses={200: StockRowSerializer(many=True)},
    )
    @action(detail=False, methods=['get'])
    def stock(self, request):
        rows = selectors.stock_rows(company=self.company)
        return Response(StockRowSerializer(rows, many=True).data)

    @extend_schema(
        summary='Download the stock report (CSV or JSON)',
        description=(
            'Returns the stock report as a file attachment, built with pandas. '
            'The parameter is called `file_format` and not `format` because '
            'DRF reserves the latter for content negotiation.'
        ),
        parameters=[
            OpenApiParameter(
                name='file_format',
                enum=['csv', 'json'],
                default='csv',
                description='Output format of the downloaded file.',
            ),
        ],
        responses={
            (200, 'text/csv'): OpenApiTypes.BINARY,
            (200, 'application/json'): OpenApiTypes.BINARY,
            400: OpenApiResponse(description='Unsupported file_format'),
        },
    )
    @action(detail=False, methods=['get'], url_path='stock/export')
    def stock_export(self, request):
        file_format = request.query_params.get('file_format', 'csv').lower()
        renderer = exports.RENDERERS.get(file_format)
        if renderer is None:
            raise ValidationError({
                'file_format': [
                    f'Unsupported format "{file_format}". '
                    f'Use one of: {", ".join(sorted(exports.RENDERERS))}.'
                ]
            })

        frame = exports.stock_dataframe(selectors.stock_rows(company=self.company))
        return renderer(frame)

    @extend_schema(
        summary='Products running out',
        description='Products whose calculated stock is at or below `min_stock_level`.',
        responses={200: ProductSerializer(many=True)},
    )
    @action(detail=False, methods=['get'], url_path='low-stock')
    def low_stock(self, request):
        products = selectors.low_stock_rows(company=self.company)
        serializer = ProductSerializer(
            products, many=True, context=self.get_serializer_context()
        )
        return Response(serializer.data)

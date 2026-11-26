"""The OpenAPI schema and the two documentation viewers."""

import json

import pytest
import yaml
from django.urls import reverse

pytestmark = pytest.mark.django_db

SCHEMA_URL = reverse('schema')
SWAGGER_URL = reverse('swagger-ui')
REDOC_URL = reverse('redoc')


@pytest.fixture
def schema(client):
    """The generated schema, parsed."""
    response = client.get(SCHEMA_URL)
    assert response.status_code == 200
    return yaml.safe_load(response.content)


class TestSchemaEndpoint:
    def test_serves_yaml_by_default(self, client):
        response = client.get(SCHEMA_URL)

        assert response.status_code == 200
        assert 'application/vnd.oai.openapi' in response['Content-Type']

    def test_serves_json_on_request(self, client):
        response = client.get(SCHEMA_URL, {'format': 'json'})

        assert response.status_code == 200
        assert json.loads(response.content)['openapi'].startswith('3.')

    def test_readable_without_signing_in(self, api_client):
        """The docs are public; the endpoints they describe are not."""
        assert api_client.get(SCHEMA_URL).status_code == 200

    def test_generates_without_warnings(self):
        """Guard against a view the generator cannot introspect."""
        from drf_spectacular.drainage import GENERATOR_STATS
        from drf_spectacular.generators import SchemaGenerator

        with GENERATOR_STATS.silence():
            SchemaGenerator().get_schema(request=None, public=True)

        assert not GENERATOR_STATS._warn_cache, dict(GENERATOR_STATS._warn_cache)
        assert not GENERATOR_STATS._error_cache, dict(GENERATOR_STATS._error_cache)


class TestSchemaContent:
    def test_metadata(self, schema):
        assert schema['info']['title'] == 'Inventory Management API'
        assert schema['info']['version'] == '1.0.0'

    def test_session_authentication_is_declared(self, schema):
        assert 'cookieAuth' in schema['components']['securitySchemes']

    @pytest.mark.parametrize('path', [
        '/api/auth/register/',
        '/api/auth/login/',
        '/api/auth/logout/',
        '/api/auth/password-reset/',
        '/api/auth/password-reset/confirm/',
        '/api/warehouses/',
        '/api/warehouses/{id}/',
        '/api/warehouses/{id}/stock/',
        '/api/products/',
        '/api/products/{id}/',
        '/api/products/{id}/restore/',
        '/api/products/{id}/stock/',
        '/api/transactions/',
        '/api/transactions/{id}/',
        '/api/reports/warehouse-value/',
        '/api/reports/stock/',
        '/api/reports/stock/export/',
        '/api/reports/low-stock/',
    ])
    def test_endpoint_is_documented(self, schema, path):
        assert path in schema['paths']

    def test_every_operation_has_a_summary(self, schema):
        missing = [
            f'{method.upper()} {path}'
            for path, operations in schema['paths'].items()
            for method, operation in operations.items()
            if not operation.get('summary')
        ]
        assert missing == []

    def test_ledger_is_documented_as_append_only(self, schema):
        """No PUT/PATCH/DELETE should be advertised for transactions."""
        methods = set(schema['paths']['/api/transactions/{id}/'])

        assert methods == {'get'}

    def test_transaction_type_enum(self, schema):
        enum = schema['components']['schemas']['TransactionTypeEnum']

        assert enum['enum'] == ['IN', 'OUT', 'TRANSFER']

    def test_search_filter_and_pagination_parameters(self, schema):
        names = {p['name'] for p in schema['paths']['/api/products/']['get']['parameters']}

        assert {'search', 'ordering', 'page', 'page_size', 'low_stock', 'min_price'} <= names

    def test_transaction_filter_parameters(self, schema):
        names = {p['name'] for p in schema['paths']['/api/transactions/']['get']['parameters']}

        assert {'transaction_type', 'warehouse', 'date_from', 'date_to', 'sku'} <= names

    def test_calculated_fields_are_documented(self, schema):
        properties = schema['components']['schemas']['Product']['properties']

        assert {'total_stock', 'total_value', 'is_low_stock'} <= set(properties)

    def test_rate_limited_endpoint_documents_429(self, schema):
        responses = schema['paths']['/api/transactions/']['post']['responses']

        assert '429' in responses

    def test_export_declares_both_file_formats(self, schema):
        operation = schema['paths']['/api/reports/stock/export/']['get']
        content = operation['responses']['200']['content']

        assert set(content) == {'text/csv', 'application/json'}
        assert {'csv', 'json'} == set(
            next(p for p in operation['parameters'] if p['name'] == 'file_format')['schema']['enum']
        )

    def test_custom_list_actions_are_paginated(self, schema):
        schema_ref = (
            schema['paths']['/api/warehouses/{id}/stock/']['get']
            ['responses']['200']['content']['application/json']['schema']['$ref']
        )

        assert schema_ref.endswith('PaginatedProductList')


class TestDocumentationViewers:
    def test_swagger_ui_renders(self, client):
        response = client.get(SWAGGER_URL)

        assert response.status_code == 200
        assert b'swagger-ui' in response.content

    def test_swagger_ui_sets_the_csrf_cookie(self, client):
        """The request interceptor reads this cookie for "Try it out".."""
        response = client.get(SWAGGER_URL)

        assert 'csrftoken' in response.cookies

    def test_swagger_assets_are_self_hosted(self, client):
        """No CDN, so the docs work offline and inside Docker."""
        body = client.get(SWAGGER_URL).content.decode()

        assert 'unpkg.com' not in body
        assert 'cdn.jsdelivr.net' not in body

    def test_redoc_renders(self, client):
        response = client.get(REDOC_URL)

        assert response.status_code == 200
        assert b'redoc' in response.content.lower()

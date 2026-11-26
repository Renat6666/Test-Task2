"""Reports: the Redis cached warehouse value report and the exports."""

import csv
import io
import json
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.common.cache import warehouse_value_report_key
from tests.conftest import IN, OUT, TRANSFER

pytestmark = pytest.mark.django_db

VALUE_URL = reverse('report-warehouse-value')
STOCK_URL = reverse('report-stock')
EXPORT_URL = reverse('report-stock-export')
LOW_STOCK_URL = reverse('report-low-stock')
TRANSACTION_URL = reverse('transaction-list')


class TestWarehouseValueReport:
    def test_totals_per_warehouse(
        self, client, product, second_product, warehouse, second_warehouse, record_movement
    ):
        record_movement(
            product=product, transaction_type=IN, quantity='10', destination=warehouse
        )
        record_movement(
            product=second_product, transaction_type=IN, quantity='4', destination=second_warehouse
        )

        response = client.get(VALUE_URL)

        assert response.status_code == 200
        rows = {row['name']: row for row in response.data['warehouses']}
        assert rows['Central']['total_value'] == '100.00'  # 10 * 10.00
        assert rows['North']['total_value'] == '10.00'  # 4 * 2.50
        assert response.data['total_value'] == '110.00'

    def test_empty_warehouses_are_listed_with_zeros(self, client, warehouse):
        response = client.get(VALUE_URL)

        assert response.data['warehouses'][0]['total_value'] == '0.00'
        assert response.data['total_value'] == '0.00'

    def test_soft_deleted_products_drop_out_of_the_value(
        self, client, product, stocked_warehouse
    ):
        assert client.get(VALUE_URL).data['total_value'] == '1000.00'

        client.delete(reverse('product-detail', args=[product.pk]))

        assert client.get(VALUE_URL, {'refresh': 'true'}).data['total_value'] == '0.00'

    def test_report_is_scoped_to_the_company(self, other_client, stocked_warehouse):
        response = other_client.get(VALUE_URL)

        assert response.data['warehouses'] == []
        assert response.data['total_value'] == '0.00'


class TestWarehouseValueReportCache:
    def test_first_call_computes_and_second_call_is_cached(self, client, stocked_warehouse):
        first = client.get(VALUE_URL)
        second = client.get(VALUE_URL)

        assert first.data['cached'] is False
        assert second.data['cached'] is True
        assert second.data['generated_at'] == first.data['generated_at']

    def test_result_is_stored_in_redis(self, client, company, stocked_warehouse):
        from django.core.cache import cache

        assert cache.get(warehouse_value_report_key(company.pk)) is None

        client.get(VALUE_URL)

        assert cache.get(warehouse_value_report_key(company.pk)) is not None

    def test_refresh_bypasses_the_cache(self, client, stocked_warehouse):
        client.get(VALUE_URL)

        response = client.get(VALUE_URL, {'refresh': 'true'})

        assert response.data['cached'] is False

    def test_a_new_transaction_invalidates_the_cache(
        self, client, company, product, stocked_warehouse, django_capture_on_commit_callbacks
    ):
        from django.core.cache import cache

        assert client.get(VALUE_URL).data['total_value'] == '1000.00'
        assert client.get(VALUE_URL).data['cached'] is True

        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(TRANSACTION_URL, {
                'product': product.pk,
                'transaction_type': OUT,
                'quantity': '40',
                'source_warehouse': stocked_warehouse.pk,
            })
        assert response.status_code == 201

        assert cache.get(warehouse_value_report_key(company.pk)) is None

        fresh = client.get(VALUE_URL)
        assert fresh.data['cached'] is False
        assert fresh.data['total_value'] == '600.00'

    def test_a_price_change_invalidates_the_cache(
        self, client, company, product, stocked_warehouse, django_capture_on_commit_callbacks
    ):
        from django.core.cache import cache

        client.get(VALUE_URL)

        with django_capture_on_commit_callbacks(execute=True):
            client.patch(
                reverse('product-detail', args=[product.pk]), {'base_price': '1.00'}
            )

        assert cache.get(warehouse_value_report_key(company.pk)) is None
        assert client.get(VALUE_URL).data['total_value'] == '100.00'

    def test_caches_are_not_shared_between_companies(
        self, client, other_client, stocked_warehouse
    ):
        assert client.get(VALUE_URL).data['total_value'] == '1000.00'
        assert other_client.get(VALUE_URL).data['total_value'] == '0.00'


class TestStockReport:
    def test_lists_every_product_with_its_stock(
        self, client, product, second_product, stocked_warehouse
    ):
        response = client.get(STOCK_URL)

        assert response.status_code == 200
        rows = {row['sku']: row for row in response.data}
        assert rows['SKU-001']['total_stock'] == '100.000'
        assert rows['SKU-001']['total_value'] == '1000.00'
        assert rows['SKU-001']['is_low_stock'] is False
        assert rows['SKU-002']['total_stock'] == '0.000'
        assert rows['SKU-002']['is_low_stock'] is True

    def test_low_stock_report(self, client, product, stocked_warehouse, record_movement):
        record_movement(
            product=product, transaction_type=OUT, quantity='96', source=stocked_warehouse
        )

        response = client.get(LOW_STOCK_URL)

        assert [row['sku'] for row in response.data] == ['SKU-001']
        assert Decimal(response.data[0]['total_stock']) == Decimal('4.000')


class TestStockExport:
    def test_csv_export(self, client, product, second_product, stocked_warehouse):
        response = client.get(EXPORT_URL, {'file_format': 'csv'})

        assert response.status_code == 200
        assert response['Content-Type'].startswith('text/csv')
        assert 'attachment; filename="stock-report-' in response['Content-Disposition']

        rows = list(csv.DictReader(io.StringIO(response.content.decode())))

        assert [row['sku'] for row in rows] == ['SKU-001', 'SKU-002']
        assert rows[0]['total_stock'] == '100.000'
        assert rows[0]['total_value'] == '1000.00'
        assert rows[0]['name'] == 'Blue widget'

    def test_csv_is_the_default_format(self, client, product):
        response = client.get(EXPORT_URL)

        assert response['Content-Type'].startswith('text/csv')

    def test_json_export(self, client, product, stocked_warehouse):
        response = client.get(EXPORT_URL, {'file_format': 'json'})

        assert response.status_code == 200
        assert response['Content-Type'] == 'application/json'

        rows = json.loads(response.content)

        assert len(rows) == 1
        assert rows[0]['sku'] == 'SKU-001'
        assert rows[0]['total_stock'] == '100.000'
        assert rows[0]['is_low_stock'] is False

    def test_unsupported_format_is_rejected(self, client):
        response = client.get(EXPORT_URL, {'file_format': 'xlsx'})

        assert response.status_code == 400
        assert 'file_format' in response.data

    def test_export_is_scoped_to_the_company(self, other_client, product, stocked_warehouse):
        response = other_client.get(EXPORT_URL, {'file_format': 'json'})

        assert json.loads(response.content) == []

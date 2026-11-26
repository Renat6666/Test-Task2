"""Product CRUD, soft delete, search, filtering, ordering and pagination."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.products.models import Product
from tests.conftest import IN, OUT

pytestmark = pytest.mark.django_db

LIST_URL = reverse('product-list')


def detail_url(product_id):
    return reverse('product-detail', args=[product_id])


def payload(**overrides):
    body = {
        'sku': 'SKU-NEW',
        'name': 'Green thing',
        'description': 'A thing, in green.',
        'base_price': '19.99',
        'min_stock_level': '3.000',
    }
    body.update(overrides)
    return body


class TestProductCrud:
    def test_create(self, client, company):
        response = client.post(LIST_URL, payload())

        assert response.status_code == 201
        assert response.data['sku'] == 'SKU-NEW'
        assert response.data['total_stock'] == '0.000'
        assert response.data['total_value'] == '0.00'
        assert Product.objects.get(pk=response.data['id']).company == company

    def test_create_validates_required_fields(self, client):
        response = client.post(LIST_URL, {})

        assert response.status_code == 400
        assert {'sku', 'name', 'base_price'} <= set(response.data)

    def test_negative_price_is_rejected(self, client):
        response = client.post(LIST_URL, payload(base_price='-1.00'))

        assert response.status_code == 400
        assert 'base_price' in response.data

    def test_duplicate_sku_is_rejected(self, client, product):
        response = client.post(LIST_URL, payload(sku=product.sku))

        assert response.status_code == 400
        assert 'sku' in response.data

    def test_same_sku_in_another_company_is_fine(self, other_client, product):
        response = other_client.post(LIST_URL, payload(sku=product.sku))

        assert response.status_code == 201

    def test_retrieve(self, client, product):
        response = client.get(detail_url(product.pk))

        assert response.status_code == 200
        assert response.data['name'] == 'Blue widget'

    def test_update(self, client, product):
        response = client.patch(detail_url(product.pk), {'base_price': '12.50'})

        assert response.status_code == 200
        assert response.data['base_price'] == '12.50'

    def test_price_change_is_reflected_in_the_stock_value(
        self, client, product, stocked_warehouse
    ):
        client.patch(detail_url(product.pk), {'base_price': '1.00'})

        response = client.get(detail_url(product.pk))

        assert response.data['total_stock'] == '100.000'
        assert response.data['total_value'] == '100.00'

    def test_scoped_to_the_company(self, other_client, product):
        assert other_client.get(detail_url(product.pk)).status_code == 404


class TestSoftDelete:
    def test_delete_is_a_soft_delete(self, client, product):
        response = client.delete(detail_url(product.pk))

        assert response.status_code == 204
        product.refresh_from_db()
        assert product.is_deleted is True
        assert product.deleted_at is not None

    def test_deleted_products_leave_the_catalogue(self, client, product):
        client.delete(detail_url(product.pk))

        assert client.get(LIST_URL).data['count'] == 0

    def test_deleted_products_can_still_be_opened(self, client, product):
        client.delete(detail_url(product.pk))

        response = client.get(detail_url(product.pk))

        assert response.status_code == 200
        assert response.data['is_deleted'] is True

    def test_history_survives_the_delete(
        self, client, product, stocked_warehouse, record_movement
    ):
        record_movement(
            product=product, transaction_type=OUT, quantity='10', source=stocked_warehouse
        )
        client.delete(detail_url(product.pk))

        transactions = client.get(reverse('transaction-list')).data

        assert transactions['count'] == 2
        assert transactions['results'][0]['product']['sku'] == 'SKU-001'

    def test_include_deleted_brings_them_back_to_the_list(self, client, product):
        client.delete(detail_url(product.pk))

        response = client.get(LIST_URL, {'include_deleted': 'true'})

        assert response.data['count'] == 1

    def test_sku_can_be_reused_after_a_delete(self, client, product):
        client.delete(detail_url(product.pk))

        response = client.post(LIST_URL, payload(sku=product.sku))

        assert response.status_code == 201

    def test_a_deleted_product_cannot_be_edited(self, client, product):
        client.delete(detail_url(product.pk))

        response = client.patch(detail_url(product.pk), {'name': 'Nope'})

        assert response.status_code == 409

    def test_restore(self, client, product):
        client.delete(detail_url(product.pk))

        response = client.post(reverse('product-restore', args=[product.pk]))

        assert response.status_code == 200
        assert response.data['is_deleted'] is False
        assert client.get(LIST_URL).data['count'] == 1


class TestSearchFilterSort:
    @pytest.fixture(autouse=True)
    def catalogue(self, product, second_product):
        return product, second_product

    def test_search_by_name(self, client):
        response = client.get(LIST_URL, {'search': 'gadget'})

        assert [row['sku'] for row in response.data['results']] == ['SKU-002']

    def test_search_by_sku(self, client):
        response = client.get(LIST_URL, {'search': 'SKU-001'})

        assert [row['sku'] for row in response.data['results']] == ['SKU-001']

    def test_search_is_case_insensitive_and_partial(self, client):
        response = client.get(LIST_URL, {'search': 'WIDG'})

        assert [row['sku'] for row in response.data['results']] == ['SKU-001']

    def test_filter_by_price_range(self, client):
        response = client.get(LIST_URL, {'min_price': '5'})

        assert [row['sku'] for row in response.data['results']] == ['SKU-001']

    def test_order_by_price(self, client):
        response = client.get(LIST_URL, {'ordering': 'base_price'})

        assert [row['sku'] for row in response.data['results']] == ['SKU-002', 'SKU-001']

    def test_order_by_total_stock(
        self, client, product, second_product, warehouse, record_movement
    ):
        record_movement(
            product=second_product, transaction_type=IN, quantity='7', destination=warehouse
        )

        response = client.get(LIST_URL, {'ordering': '-total_stock'})

        assert [row['sku'] for row in response.data['results']] == ['SKU-002', 'SKU-001']

    def test_order_by_total_value(
        self, client, product, second_product, warehouse, record_movement
    ):
        # 7 * 2.50 = 17.50 against 1 * 10.00 = 10.00
        record_movement(
            product=second_product, transaction_type=IN, quantity='7', destination=warehouse
        )
        record_movement(
            product=product, transaction_type=IN, quantity='1', destination=warehouse
        )

        response = client.get(LIST_URL, {'ordering': '-total_value'})

        assert [row['sku'] for row in response.data['results']] == ['SKU-002', 'SKU-001']

    def test_filter_low_stock(self, client, product, second_product):
        # Nothing has been received yet, so SKU-001 (min 5) is below its level
        # while SKU-002 (min 0) is exactly at it.
        response = client.get(LIST_URL, {'low_stock': 'true', 'ordering': 'sku'})

        assert [row['sku'] for row in response.data['results']] == ['SKU-001', 'SKU-002']

    def test_filter_in_stock(self, client, product, warehouse, record_movement):
        record_movement(
            product=product, transaction_type=IN, quantity='2', destination=warehouse
        )

        response = client.get(LIST_URL, {'in_stock': 'true'})

        assert [row['sku'] for row in response.data['results']] == ['SKU-001']


class TestPagination:
    def test_results_are_paginated(self, client, company):
        Product.objects.bulk_create(
            Product(
                company=company,
                sku=f'BULK-{index:03d}',
                name=f'Item {index}',
                base_price=Decimal('1.00'),
            )
            for index in range(25)
        )

        first = client.get(LIST_URL)

        assert first.data['count'] == 25
        assert len(first.data['results']) == 20
        assert first.data['next'] is not None

        second = client.get(LIST_URL, {'page': 2})

        assert len(second.data['results']) == 5

    def test_page_size_can_be_overridden(self, client, product, second_product):
        response = client.get(LIST_URL, {'page_size': 1})

        assert len(response.data['results']) == 1
        assert response.data['count'] == 2


class TestProductStockBreakdown:
    def test_stock_per_warehouse(
        self, client, product, warehouse, second_warehouse, record_movement
    ):
        record_movement(
            product=product, transaction_type=IN, quantity='10', destination=warehouse
        )
        record_movement(
            product=product, transaction_type=IN, quantity='4', destination=second_warehouse
        )

        response = client.get(reverse('product-stock', args=[product.pk]))

        assert response.status_code == 200
        assert response.data == [
            {'warehouse_id': warehouse.pk, 'warehouse_name': 'Central', 'quantity': '10.000'},
            {'warehouse_id': second_warehouse.pk, 'warehouse_name': 'North', 'quantity': '4.000'},
        ]

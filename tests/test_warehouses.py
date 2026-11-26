"""Warehouse CRUD, company scoping and the per-warehouse stock view."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.warehouses.models import Warehouse
from tests.conftest import IN, OUT, TRANSFER

pytestmark = pytest.mark.django_db

LIST_URL = reverse('warehouse-list')


def detail_url(warehouse_id):
    return reverse('warehouse-detail', args=[warehouse_id])


class TestWarehouseCrud:
    def test_create(self, client, company):
        response = client.post(LIST_URL, {'name': 'South', 'address': '3 South Ave'})

        assert response.status_code == 201
        assert response.data['name'] == 'South'
        assert response.data['total_value'] == '0.00'

        warehouse = Warehouse.objects.get(pk=response.data['id'])
        assert warehouse.company == company

    def test_create_requires_name_and_address(self, client):
        response = client.post(LIST_URL, {})

        assert response.status_code == 400
        assert set(response.data) == {'name', 'address'}

    def test_duplicate_name_is_rejected(self, client, warehouse):
        response = client.post(LIST_URL, {'name': warehouse.name, 'address': 'x'})

        assert response.status_code == 400
        assert 'name' in response.data

    def test_list_is_paginated(self, client, warehouse, second_warehouse):
        response = client.get(LIST_URL)

        assert response.status_code == 200
        assert response.data['count'] == 2
        assert {row['name'] for row in response.data['results']} == {'Central', 'North'}

    def test_retrieve(self, client, warehouse):
        response = client.get(detail_url(warehouse.pk))

        assert response.status_code == 200
        assert response.data['manager_username'] == 'warehouse_manager'

    def test_update(self, client, warehouse):
        response = client.patch(detail_url(warehouse.pk), {'address': '9 New Rd'})

        assert response.status_code == 200
        assert response.data['address'] == '9 New Rd'
        warehouse.refresh_from_db()
        assert warehouse.address == '9 New Rd'

    def test_manager_must_be_a_colleague(self, client, warehouse, other_employee):
        response = client.patch(detail_url(warehouse.pk), {'manager': other_employee.pk})

        assert response.status_code == 400
        assert 'manager' in response.data

    def test_delete_an_unused_warehouse(self, client, warehouse):
        response = client.delete(detail_url(warehouse.pk))

        assert response.status_code == 204
        assert not Warehouse.objects.filter(pk=warehouse.pk).exists()

    def test_delete_is_refused_once_stock_moved(self, client, stocked_warehouse):
        response = client.delete(detail_url(stocked_warehouse.pk))

        assert response.status_code == 409
        assert Warehouse.objects.filter(pk=stocked_warehouse.pk).exists()

    def test_retiring_a_warehouse_instead(self, client, stocked_warehouse):
        response = client.patch(detail_url(stocked_warehouse.pk), {'is_active': False})

        assert response.status_code == 200
        assert response.data['is_active'] is False


class TestWarehouseScoping:
    def test_other_companies_warehouses_are_invisible(self, other_client, warehouse):
        assert other_client.get(detail_url(warehouse.pk)).status_code == 404
        assert other_client.get(LIST_URL).data['count'] == 0

    def test_other_companies_warehouses_cannot_be_edited(self, other_client, warehouse):
        response = other_client.patch(detail_url(warehouse.pk), {'name': 'Hijacked'})

        assert response.status_code == 404


class TestWarehouseTotals:
    def test_totals_are_calculated_from_the_ledger(
        self, client, warehouse, product, record_movement
    ):
        record_movement(
            product=product, transaction_type=IN, quantity='12', destination=warehouse
        )

        response = client.get(detail_url(warehouse.pk))

        assert response.data['total_quantity'] == '12.000'
        assert response.data['total_value'] == '120.00'  # 12 * 10.00

    def test_transfer_moves_value_between_warehouses(
        self, client, stocked_warehouse, second_warehouse, product, record_movement
    ):
        record_movement(
            product=product,
            transaction_type=TRANSFER,
            quantity='40',
            source=stocked_warehouse,
            destination=second_warehouse,
        )

        rows = {row['name']: row for row in client.get(LIST_URL).data['results']}

        assert rows['Central']['total_quantity'] == '60.000'
        assert rows['North']['total_quantity'] == '40.000'
        assert rows['Central']['total_value'] == '600.00'
        assert rows['North']['total_value'] == '400.00'

    def test_warehouse_stock_lists_products_held_there(
        self, client, stocked_warehouse, second_product, record_movement
    ):
        record_movement(
            product=second_product,
            transaction_type=IN,
            quantity='4',
            destination=stocked_warehouse,
        )

        response = client.get(reverse('warehouse-stock', args=[stocked_warehouse.pk]))

        assert response.status_code == 200
        rows = {row['sku']: row for row in response.data['results']}
        assert rows['SKU-001']['total_stock'] == '100.000'
        assert rows['SKU-002']['total_stock'] == '4.000'

    def test_warehouse_stock_is_scoped_to_that_warehouse(
        self, client, stocked_warehouse, second_warehouse, product, record_movement
    ):
        record_movement(
            product=product,
            transaction_type=TRANSFER,
            quantity='25',
            source=stocked_warehouse,
            destination=second_warehouse,
        )

        response = client.get(reverse('warehouse-stock', args=[second_warehouse.pk]))

        assert response.data['results'][0]['total_stock'] == '25.000'

    def test_warehouse_low_stock(
        self, client, stocked_warehouse, product, record_movement
    ):
        # min_stock_level is 5; ship 97 of the 100 units away.
        record_movement(
            product=product, transaction_type=OUT, quantity='97', source=stocked_warehouse
        )

        response = client.get(reverse('warehouse-low-stock', args=[stocked_warehouse.pk]))

        assert response.status_code == 200
        assert [row['sku'] for row in response.data['results']] == ['SKU-001']
        assert Decimal(response.data['results'][0]['total_stock']) == Decimal('3.000')


class TestWarehouseFiltersAndSearch:
    def test_search_by_name(self, client, warehouse, second_warehouse):
        response = client.get(LIST_URL, {'search': 'nort'})

        assert [row['name'] for row in response.data['results']] == ['North']

    def test_filter_by_active_flag(self, client, warehouse, second_warehouse):
        second_warehouse.is_active = False
        second_warehouse.save(update_fields=['is_active'])

        response = client.get(LIST_URL, {'is_active': 'true'})

        assert [row['name'] for row in response.data['results']] == ['Central']

    def test_order_by_total_value(
        self, client, stocked_warehouse, second_warehouse, second_product, record_movement
    ):
        record_movement(
            product=second_product,
            transaction_type=IN,
            quantity='1',
            destination=second_warehouse,
        )

        response = client.get(LIST_URL, {'ordering': '-total_value'})

        assert [row['name'] for row in response.data['results']] == ['Central', 'North']

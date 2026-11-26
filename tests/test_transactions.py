"""Stock movements: validation, balances, filtering and rate limiting."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.transactions.models import InventoryEntry, InventoryTransaction
from apps.transactions.throttles import TransactionCreateThrottle
from tests.conftest import IN, OUT, TRANSFER

pytestmark = pytest.mark.django_db

LIST_URL = reverse('transaction-list')
PRODUCT_LIST_URL = reverse('product-list')


def stock_of(client, product):
    """Read the calculated stock of a product back through the API."""
    response = client.get(reverse('product-detail', args=[product.pk]))
    return Decimal(response.data['total_stock'])


class TestIncoming:
    def test_in_increases_the_balance(self, client, product, warehouse):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': IN,
            'quantity': '25.5',
            'destination_warehouse': warehouse.pk,
        })

        assert response.status_code == 201
        assert response.data['transaction_type'] == 'IN'
        assert response.data['created_by'] == 'warehouse_clerk'
        assert stock_of(client, product) == Decimal('25.500')

    def test_in_writes_a_single_positive_ledger_entry(self, client, product, warehouse):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': IN,
            'quantity': '10',
            'destination_warehouse': warehouse.pk,
        })

        entries = InventoryEntry.objects.filter(transaction_id=response.data['id'])
        assert [(entry.warehouse_id, entry.quantity_delta) for entry in entries] == [
            (warehouse.pk, Decimal('10.000'))
        ]

    def test_in_requires_a_destination(self, client, product):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': IN,
            'quantity': '5',
        })

        assert response.status_code == 400
        assert 'destination_warehouse' in response.data

    def test_in_refuses_a_source(self, client, product, warehouse, second_warehouse):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': IN,
            'quantity': '5',
            'source_warehouse': second_warehouse.pk,
            'destination_warehouse': warehouse.pk,
        })

        assert response.status_code == 400
        assert 'source_warehouse' in response.data


class TestOutgoing:
    def test_out_decreases_the_balance(self, client, product, stocked_warehouse):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': OUT,
            'quantity': '30',
            'source_warehouse': stocked_warehouse.pk,
        })

        assert response.status_code == 201
        assert stock_of(client, product) == Decimal('70.000')

    def test_out_is_refused_without_enough_stock(self, client, product, stocked_warehouse):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': OUT,
            'quantity': '101',
            'source_warehouse': stocked_warehouse.pk,
        })

        assert response.status_code == 400
        assert 'quantity' in response.data
        assert response.data['available_quantity'] == '100.000'
        assert InventoryTransaction.objects.count() == 1  # only the initial IN

    def test_out_is_refused_from_an_empty_warehouse(
        self, client, product, stocked_warehouse, second_warehouse
    ):
        """Stock is per warehouse: 100 on Central does not help North."""
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': OUT,
            'quantity': '1',
            'source_warehouse': second_warehouse.pk,
        })

        assert response.status_code == 400
        assert response.data['available_quantity'] == '0.000'

    def test_out_may_empty_the_warehouse_exactly(self, client, product, stocked_warehouse):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': OUT,
            'quantity': '100',
            'source_warehouse': stocked_warehouse.pk,
        })

        assert response.status_code == 201
        assert stock_of(client, product) == Decimal('0.000')

    def test_out_requires_a_source(self, client, product):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': OUT,
            'quantity': '1',
        })

        assert response.status_code == 400
        assert 'source_warehouse' in response.data


class TestTransfer:
    def test_transfer_moves_stock_and_keeps_the_total(
        self, client, product, stocked_warehouse, second_warehouse
    ):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': TRANSFER,
            'quantity': '40',
            'source_warehouse': stocked_warehouse.pk,
            'destination_warehouse': second_warehouse.pk,
        })

        assert response.status_code == 201
        assert stock_of(client, product) == Decimal('100.000')

        per_warehouse = client.get(reverse('product-stock', args=[product.pk])).data
        quantities = {row['warehouse_id']: row['quantity'] for row in per_warehouse}
        assert quantities == {
            stocked_warehouse.pk: '60.000',
            second_warehouse.pk: '40.000',
        }

    def test_transfer_writes_a_balanced_pair_of_entries(
        self, client, product, stocked_warehouse, second_warehouse
    ):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': TRANSFER,
            'quantity': '15',
            'source_warehouse': stocked_warehouse.pk,
            'destination_warehouse': second_warehouse.pk,
        })

        entries = InventoryEntry.objects.filter(transaction_id=response.data['id'])
        assert sorted(entry.quantity_delta for entry in entries) == [
            Decimal('-15.000'),
            Decimal('15.000'),
        ]

    def test_transfer_is_refused_without_enough_stock(
        self, client, product, stocked_warehouse, second_warehouse
    ):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': TRANSFER,
            'quantity': '150',
            'source_warehouse': stocked_warehouse.pk,
            'destination_warehouse': second_warehouse.pk,
        })

        assert response.status_code == 400
        assert 'quantity' in response.data

    def test_transfer_needs_two_warehouses(self, client, product, stocked_warehouse):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': TRANSFER,
            'quantity': '1',
            'source_warehouse': stocked_warehouse.pk,
        })

        assert response.status_code == 400
        assert 'destination_warehouse' in response.data

    def test_transfer_to_the_same_warehouse_is_refused(
        self, client, product, stocked_warehouse
    ):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': TRANSFER,
            'quantity': '1',
            'source_warehouse': stocked_warehouse.pk,
            'destination_warehouse': stocked_warehouse.pk,
        })

        assert response.status_code == 400
        assert 'destination_warehouse' in response.data


class TestValidation:
    def test_quantity_must_be_positive(self, client, product, warehouse):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': IN,
            'quantity': '0',
            'destination_warehouse': warehouse.pk,
        })

        assert response.status_code == 400
        assert 'quantity' in response.data

    def test_unknown_transaction_type(self, client, product, warehouse):
        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': 'SHRINKAGE',
            'quantity': '1',
            'destination_warehouse': warehouse.pk,
        })

        assert response.status_code == 400
        assert 'transaction_type' in response.data

    def test_another_companys_product_is_unknown(self, other_client, product, warehouse):
        response = other_client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': IN,
            'quantity': '1',
            'destination_warehouse': warehouse.pk,
        })

        assert response.status_code == 400
        assert 'product' in response.data

    def test_a_deleted_product_cannot_move(self, client, product, warehouse):
        client.delete(reverse('product-detail', args=[product.pk]))

        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': IN,
            'quantity': '1',
            'destination_warehouse': warehouse.pk,
        })

        assert response.status_code == 400
        assert 'product' in response.data

    def test_an_inactive_warehouse_cannot_receive_stock(self, client, product, warehouse):
        warehouse.is_active = False
        warehouse.save(update_fields=['is_active'])

        response = client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': IN,
            'quantity': '1',
            'destination_warehouse': warehouse.pk,
        })

        assert response.status_code == 400
        assert 'destination_warehouse' in response.data


class TestLedgerIsAppendOnly:
    def test_transactions_cannot_be_edited(self, client, stocked_warehouse, product):
        transaction_id = InventoryTransaction.objects.get().pk

        url = reverse('transaction-detail', args=[transaction_id])

        assert client.put(url, {'quantity': '1'}).status_code == 405
        assert client.patch(url, {'quantity': '1'}).status_code == 405
        assert client.delete(url).status_code == 405


class TestTransactionReads:
    def test_detail_includes_the_ledger_entries(
        self, client, product, stocked_warehouse, second_warehouse, record_movement
    ):
        movement = record_movement(
            product=product,
            transaction_type=TRANSFER,
            quantity='5',
            source=stocked_warehouse,
            destination=second_warehouse,
        )

        response = client.get(reverse('transaction-detail', args=[movement.pk]))

        assert response.status_code == 200
        deltas = {entry['warehouse']['name']: entry['quantity_delta'] for entry in response.data['entries']}
        assert deltas == {'Central': '-5.000', 'North': '5.000'}

    def test_scoped_to_the_company(self, other_client, stocked_warehouse):
        assert other_client.get(LIST_URL).data['count'] == 0

    def test_newest_first(self, client, product, stocked_warehouse, record_movement):
        record_movement(
            product=product, transaction_type=OUT, quantity='1', source=stocked_warehouse
        )

        types = [row['transaction_type'] for row in client.get(LIST_URL).data['results']]

        assert types == ['OUT', 'IN']


class TestTransactionFilters:
    @pytest.fixture(autouse=True)
    def ledger(self, product, second_product, warehouse, second_warehouse, record_movement):
        record_movement(
            product=product, transaction_type=IN, quantity='100', destination=warehouse
        )
        record_movement(
            product=second_product, transaction_type=IN, quantity='50', destination=second_warehouse
        )
        record_movement(
            product=product, transaction_type=OUT, quantity='10', source=warehouse
        )
        record_movement(
            product=product,
            transaction_type=TRANSFER,
            quantity='20',
            source=warehouse,
            destination=second_warehouse,
        )

    def test_filter_by_type(self, client):
        response = client.get(LIST_URL, {'transaction_type': 'IN'})

        assert response.data['count'] == 2

    def test_filter_by_several_types(self, client):
        response = client.get(LIST_URL, {'transaction_type': ['OUT', 'TRANSFER']})

        assert response.data['count'] == 2

    def test_filter_by_warehouse_matches_both_directions(self, client, second_warehouse):
        response = client.get(LIST_URL, {'warehouse': second_warehouse.pk})

        # The IN on North plus the TRANSFER that targets it.
        assert response.data['count'] == 2

    def test_filter_by_source_warehouse(self, client, warehouse):
        response = client.get(LIST_URL, {'source_warehouse': warehouse.pk})

        assert response.data['count'] == 2

    def test_filter_by_product(self, client, second_product):
        response = client.get(LIST_URL, {'product': second_product.pk})

        assert response.data['count'] == 1

    def test_filter_by_sku(self, client):
        response = client.get(LIST_URL, {'sku': 'SKU-002'})

        assert response.data['count'] == 1

    def test_filter_by_date_range(self, client):
        from django.utils import timezone

        tomorrow = (timezone.now() + timezone.timedelta(days=1)).isoformat()
        yesterday = (timezone.now() - timezone.timedelta(days=1)).isoformat()

        assert client.get(LIST_URL, {'date_from': tomorrow}).data['count'] == 0
        assert client.get(LIST_URL, {'date_to': yesterday}).data['count'] == 0
        assert client.get(
            LIST_URL, {'date_from': yesterday, 'date_to': tomorrow}
        ).data['count'] == 4

    def test_search_by_product_name(self, client):
        response = client.get(LIST_URL, {'search': 'gadget'})

        assert response.data['count'] == 1


class TestRateLimit:
    """One employee may not create more than 50 transactions per minute.

    The limit is lowered to 3/min here so the test stays fast; the production
    value is asserted separately below.
    """

    @pytest.fixture
    def tight_limit(self, monkeypatch):
        # DRF binds THROTTLE_RATES onto the class at import time, so the rate
        # is lowered there rather than through the settings.
        monkeypatch.setattr(
            TransactionCreateThrottle,
            'THROTTLE_RATES',
            {'transaction_create': '3/min'},
        )

    def test_configured_production_rate(self, settings):
        assert settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']['transaction_create'] == '50/min'

    def test_counters_are_kept_in_redis(
        self, tight_limit, client, employee, product, warehouse, settings
    ):
        from django.core.cache import cache

        assert 'redis' in settings.CACHES['default']['BACKEND'].lower()

        client.post(LIST_URL, {
            'product': product.pk,
            'transaction_type': IN,
            'quantity': '1',
            'destination_warehouse': warehouse.pk,
        })

        key = f'throttle_transaction_create_{employee.pk}'
        assert len(cache.get(key) or []) == 1

    def test_creating_too_many_transactions_is_throttled(
        self, tight_limit, client, product, warehouse
    ):
        body = {
            'product': product.pk,
            'transaction_type': IN,
            'quantity': '1',
            'destination_warehouse': warehouse.pk,
        }

        statuses = [client.post(LIST_URL, body).status_code for _ in range(4)]

        assert statuses == [201, 201, 201, 429]
        assert InventoryTransaction.objects.count() == 3

    def test_reading_transactions_is_not_throttled(
        self, tight_limit, client, product, warehouse
    ):
        body = {
            'product': product.pk,
            'transaction_type': IN,
            'quantity': '1',
            'destination_warehouse': warehouse.pk,
        }
        for _ in range(3):
            client.post(LIST_URL, body)

        assert all(client.get(LIST_URL).status_code == 200 for _ in range(5))

    def test_the_limit_is_per_employee(
        self, tight_limit, client, api_client, manager, product, warehouse
    ):
        body = {
            'product': product.pk,
            'transaction_type': IN,
            'quantity': '1',
            'destination_warehouse': warehouse.pk,
        }
        for _ in range(3):
            client.post(LIST_URL, body)
        assert client.post(LIST_URL, body).status_code == 429

        api_client.force_authenticate(user=manager)
        assert api_client.post(LIST_URL, body).status_code == 201

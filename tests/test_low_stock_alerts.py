"""Bonus task: email the warehouse manager when an article runs low."""

import pytest
from django.core import mail
from django.urls import reverse

from tests.conftest import IN, OUT, TRANSFER

pytestmark = pytest.mark.django_db

TRANSACTION_URL = reverse('transaction-list')


def ship(client, *, product, warehouse, quantity):
    return client.post(TRANSACTION_URL, {
        'product': product.pk,
        'transaction_type': OUT,
        'quantity': str(quantity),
        'source_warehouse': warehouse.pk,
    })


class TestLowStockAlert:
    def test_alert_is_sent_when_the_balance_drops_below_the_minimum(
        self, client, product, stocked_warehouse, manager, django_capture_on_commit_callbacks
    ):
        # min_stock_level is 5, so shipping 96 of 100 leaves 4.
        with django_capture_on_commit_callbacks(execute=True):
            response = ship(client, product=product, warehouse=stocked_warehouse, quantity=96)

        assert response.status_code == 201
        assert len(mail.outbox) == 1

        message = mail.outbox[0]
        assert message.to == [manager.email]
        assert 'SKU-001' in message.subject
        assert 'Central' in message.subject
        assert 'Remaining:     4.000' in message.body

    def test_no_alert_while_the_balance_stays_above_the_minimum(
        self, client, product, stocked_warehouse, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            ship(client, product=product, warehouse=stocked_warehouse, quantity=10)

        assert mail.outbox == []

    def test_exactly_at_the_minimum_does_not_alert(
        self, client, product, stocked_warehouse, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            ship(client, product=product, warehouse=stocked_warehouse, quantity=95)

        assert mail.outbox == []

    def test_incoming_stock_never_alerts(
        self, client, product, warehouse, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            client.post(TRANSACTION_URL, {
                'product': product.pk,
                'transaction_type': IN,
                'quantity': '1',
                'destination_warehouse': warehouse.pk,
            })

        assert mail.outbox == []

    def test_a_refused_shipment_sends_nothing(
        self, client, product, stocked_warehouse, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            response = ship(
                client, product=product, warehouse=stocked_warehouse, quantity=500
            )

        assert response.status_code == 400
        assert mail.outbox == []

    def test_falls_back_to_the_company_staff_without_a_manager(
        self, client, product, second_warehouse, manager, record_movement,
        django_capture_on_commit_callbacks,
    ):
        record_movement(
            product=product, transaction_type=IN, quantity='10', destination=second_warehouse
        )

        with django_capture_on_commit_callbacks(execute=True):
            ship(client, product=product, warehouse=second_warehouse, quantity=9)

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [manager.email]  # the only staff member

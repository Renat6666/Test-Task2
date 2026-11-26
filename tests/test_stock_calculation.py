"""The hard requirement: balances are never stored, always derived.

These tests pin down that there is no stock column anywhere and that the
calculated balances follow the ledger under every transaction type.
"""

from decimal import Decimal

import pytest
from django.db import connection

from apps.products import selectors as product_selectors
from apps.products.models import Product
from apps.transactions import selectors as transaction_selectors
from apps.warehouses.models import Warehouse
from tests.conftest import IN, OUT, TRANSFER

pytestmark = pytest.mark.django_db


class TestNoStoredBalance:
    def test_no_stock_field_on_the_models(self):
        for model in (Product, Warehouse):
            names = {field.name for field in model._meta.get_fields()}
            assert not {'stock', 'quantity', 'total_stock', 'balance'} & names, (
                f'{model.__name__} must not store a balance.'
            )

    def test_no_stock_column_in_the_database(self):
        with connection.cursor() as cursor:
            product_columns = {
                column.name for column in connection.introspection.get_table_description(
                    cursor, 'products'
                )
            }
            warehouse_columns = {
                column.name for column in connection.introspection.get_table_description(
                    cursor, 'warehouses'
                )
            }

        assert 'stock' not in product_columns
        assert 'total_stock' not in product_columns
        assert 'stock' not in warehouse_columns

    def test_stock_is_an_annotation_not_a_field(self, company, product):
        plain = Product.objects.get(pk=product.pk)
        assert not hasattr(plain, 'total_stock')

        annotated = product_selectors.product_list(company=company).get(pk=product.pk)
        assert annotated.total_stock == Decimal('0.000')


class TestDerivedBalances:
    def test_sequence_of_movements(
        self, company, product, warehouse, second_warehouse, record_movement
    ):
        record_movement(
            product=product, transaction_type=IN, quantity='100', destination=warehouse
        )
        record_movement(
            product=product, transaction_type=IN, quantity='50', destination=second_warehouse
        )
        record_movement(
            product=product, transaction_type=OUT, quantity='30', source=warehouse
        )
        record_movement(
            product=product,
            transaction_type=TRANSFER,
            quantity='20',
            source=warehouse,
            destination=second_warehouse,
        )

        assert transaction_selectors.product_stock(product=product) == Decimal('120.000')
        assert transaction_selectors.product_stock(
            product=product, warehouse=warehouse
        ) == Decimal('50.000')
        assert transaction_selectors.product_stock(
            product=product, warehouse=second_warehouse
        ) == Decimal('70.000')

    def test_balance_follows_a_deleted_transaction_free_history(
        self, company, product, stocked_warehouse, record_movement
    ):
        """Deleting the product does not change what the ledger says."""
        before = transaction_selectors.product_stock(product=product)

        product.is_deleted = True
        product.save(update_fields=['is_deleted'])

        assert transaction_selectors.product_stock(product=product) == before

    def test_total_value_is_stock_times_price(
        self, company, product, warehouse, record_movement
    ):
        record_movement(
            product=product, transaction_type=IN, quantity='3', destination=warehouse
        )

        annotated = product_selectors.product_list(company=company).get(pk=product.pk)

        assert annotated.total_stock == Decimal('3.000')
        assert Decimal(annotated.total_value).quantize(Decimal('0.01')) == Decimal('30.00')

    def test_fractional_quantities(self, company, product, warehouse, record_movement):
        record_movement(
            product=product, transaction_type=IN, quantity='0.250', destination=warehouse
        )
        record_movement(
            product=product, transaction_type=IN, quantity='0.125', destination=warehouse
        )

        assert transaction_selectors.product_stock(product=product) == Decimal('0.375')

    def test_annotation_costs_one_query_for_the_whole_page(
        self, company, product, second_product, warehouse, record_movement,
        django_assert_num_queries,
    ):
        record_movement(
            product=product, transaction_type=IN, quantity='1', destination=warehouse
        )

        with django_assert_num_queries(1):
            rows = [
                (row.sku, row.total_stock)
                for row in product_selectors.product_list(company=company)
            ]

        assert dict(rows) == {'SKU-001': Decimal('1.000'), 'SKU-002': Decimal('0.000')}

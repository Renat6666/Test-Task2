"""Shared fixtures for the API test suite."""

import copy
import re
from decimal import Decimal

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.companies.models import Company
from apps.products.models import Product
from apps.transactions.models import InventoryTransaction
from apps.transactions.services import create_inventory_transaction
from apps.users.models import User
from apps.warehouses.models import Warehouse

IN = InventoryTransaction.TransactionType.IN
OUT = InventoryTransaction.TransactionType.OUT
TRANSFER = InventoryTransaction.TransactionType.TRANSFER


@pytest.fixture(autouse=True)
def isolated_redis_cache(settings):
    """Point the cache at a throwaway Redis database and flush it per test.

    The suite really does talk to Redis (that is where the throttle counters
    and the report cache live), it just never touches the application database
    index.
    """
    caches = copy.deepcopy(settings.CACHES)
    location = caches['default']['LOCATION']
    caches['default']['LOCATION'] = (
        re.sub(r'/\d+$', '/15', location)
        if re.search(r'/\d+$', location)
        else f'{location.rstrip("/")}/15'
    )
    caches['default']['KEY_PREFIX'] = 'test'
    settings.CACHES = caches

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def company(db):
    return Company.objects.create(name='Acme Logistics')


@pytest.fixture
def other_company(db):
    return Company.objects.create(name='Globex')


@pytest.fixture
def employee(company):
    user = User.objects.create_user(
        username='warehouse_clerk',
        email='clerk@acme.example',
        password='sup3r-secret-pass',
        company=company,
    )
    return user


@pytest.fixture
def manager(company):
    return User.objects.create_user(
        username='warehouse_manager',
        email='manager@acme.example',
        password='sup3r-secret-pass',
        company=company,
        is_staff=True,
    )


@pytest.fixture
def other_employee(other_company):
    return User.objects.create_user(
        username='globex_clerk',
        email='clerk@globex.example',
        password='sup3r-secret-pass',
        company=other_company,
    )


@pytest.fixture
def client(api_client, employee):
    """An API client signed in as an employee of ``company``."""
    api_client.force_authenticate(user=employee)
    return api_client


@pytest.fixture
def other_client(other_employee):
    """A second, independent client signed in at ``other_company``."""
    client = APIClient()
    client.force_authenticate(user=other_employee)
    return client


@pytest.fixture
def warehouse(company, manager):
    return Warehouse.objects.create(
        company=company, name='Central', address='1 Main St', manager=manager
    )


@pytest.fixture
def second_warehouse(company):
    return Warehouse.objects.create(company=company, name='North', address='2 North Rd')


@pytest.fixture
def product(company):
    return Product.objects.create(
        company=company,
        sku='SKU-001',
        name='Blue widget',
        base_price=Decimal('10.00'),
        min_stock_level=Decimal('5.000'),
    )


@pytest.fixture
def second_product(company):
    return Product.objects.create(
        company=company,
        sku='SKU-002',
        name='Red gadget',
        base_price=Decimal('2.50'),
        min_stock_level=Decimal('0'),
    )


@pytest.fixture
def record_movement(company, employee):
    """Record a stock movement straight through the service layer."""

    def _record(
        *, product, transaction_type, quantity, source=None, destination=None, user=None
    ):
        return create_inventory_transaction(
            company=company,
            created_by=user or employee,
            product=product,
            transaction_type=transaction_type,
            quantity=Decimal(str(quantity)),
            source_warehouse=source,
            destination_warehouse=destination,
        )

    return _record


@pytest.fixture
def stocked_warehouse(warehouse, product, record_movement):
    """``warehouse`` holding 100 units of ``product``."""
    record_movement(
        product=product, transaction_type=IN, quantity='100', destination=warehouse
    )
    return warehouse

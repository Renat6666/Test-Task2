"""Redis cache helpers for the company scoped reports.

The warehouse value report is expensive (it aggregates the whole transaction
ledger), so the result is kept in Redis. Any stock movement invalidates the
cached entry of the company it belongs to, which keeps the report accurate
without having to store balances in the database.
"""

from django.core.cache import cache

REPORT_CACHE_VERSION = 'v1'


def warehouse_value_report_key(company_id: int) -> str:
    """Cache key of the aggregated warehouse value report of one company."""
    return f'reports:{REPORT_CACHE_VERSION}:warehouse-value:company:{company_id}'


def get_cached(key):
    """Return the cached payload for ``key`` or ``None``."""
    return cache.get(key)


def set_cached(key, payload, timeout):
    """Store ``payload`` under ``key`` for ``timeout`` seconds."""
    cache.set(key, payload, timeout=timeout)


def invalidate_company_reports(company_id: int) -> None:
    """Drop every cached report of a company.

    Called whenever stock moves or whenever the data the report is built from
    changes (product price, soft delete, warehouse rename).
    """
    cache.delete(warehouse_value_report_key(company_id))

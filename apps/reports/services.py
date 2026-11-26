"""Report building, with the expensive one cached in Redis.

``warehouse_value_report`` aggregates the whole ledger, so its result is stored
in Redis. The entry is dropped whenever stock moves (see
``apps.transactions.services``) or whenever a product price / warehouse changes,
which means the cache can never serve an outdated number.
"""

from django.conf import settings
from django.utils import timezone

from apps.common import cache as cache_utils
from apps.reports import selectors


def _build_warehouse_value_report(*, company) -> dict:
    """Run the aggregation and shape it as a JSON ready payload."""
    warehouses = selectors.warehouse_value_rows(company=company)
    totals = selectors.company_totals(company=company)

    return {
        'generated_at': timezone.now().isoformat(),
        'company': {'id': company.pk, 'name': company.name},
        'total_quantity': str(totals['total_quantity']),
        'total_value': str(totals['total_value']),
        'warehouses': [
            {
                'warehouse_id': row['warehouse_id'],
                'name': row['name'],
                'address': row['address'],
                'is_active': row['is_active'],
                'total_quantity': str(row['total_quantity']),
                'total_value': str(row['total_value']),
            }
            for row in warehouses
        ],
    }


def warehouse_value_report(*, company, refresh: bool = False) -> tuple[dict, bool]:
    """Return ``(payload, from_cache)`` for the warehouse value report.

    :param refresh: recompute and overwrite the cached entry.
    """
    key = cache_utils.warehouse_value_report_key(company.pk)

    if not refresh:
        cached = cache_utils.get_cached(key)
        if cached is not None:
            return cached, True

    payload = _build_warehouse_value_report(company=company)
    cache_utils.set_cached(key, payload, timeout=settings.REPORT_CACHE_TTL)
    return payload, False


def invalidate_reports(*, company) -> None:
    """Drop the cached reports of a company."""
    cache_utils.invalidate_company_reports(company.pk)

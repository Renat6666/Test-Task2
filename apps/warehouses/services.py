"""Warehouse write operations."""

from django.db import transaction

from apps.common.cache import invalidate_company_reports
from apps.common.exceptions import BusinessRuleViolation, Conflict
from apps.warehouses import selectors
from apps.warehouses.models import Warehouse


def _resolve_manager(*, company, manager):
    """A warehouse manager has to be an employee of the same company."""
    if manager is None:
        return None
    if manager.company_id != company.pk:
        raise BusinessRuleViolation(
            {'manager': ['The manager must be an employee of your company.']}
        )
    return manager


def _assert_name_is_free(*, company, name: str, exclude_pk=None) -> None:
    clash = Warehouse.objects.filter(company=company, name__iexact=name)
    if exclude_pk is not None:
        clash = clash.exclude(pk=exclude_pk)
    if clash.exists():
        raise BusinessRuleViolation(
            {'name': [f'A warehouse called "{name}" already exists.']}
        )


@transaction.atomic
def create_warehouse(
    *,
    company,
    name: str,
    address: str,
    manager=None,
    is_active: bool = True,
) -> Warehouse:
    """Create a warehouse for a company."""
    name = name.strip()
    _assert_name_is_free(company=company, name=name)

    warehouse = Warehouse.objects.create(
        company=company,
        name=name,
        address=address.strip(),
        manager=_resolve_manager(company=company, manager=manager),
        is_active=is_active,
    )
    transaction.on_commit(lambda: invalidate_company_reports(company.pk))
    return warehouse


@transaction.atomic
def update_warehouse(*, warehouse: Warehouse, **fields) -> Warehouse:
    """Update a warehouse."""
    editable = {'name', 'address', 'manager', 'is_active'}
    unknown = set(fields) - editable
    assert not unknown, f'Not editable: {sorted(unknown)}'

    if 'name' in fields:
        fields['name'] = fields['name'].strip()
        _assert_name_is_free(
            company=warehouse.company, name=fields['name'], exclude_pk=warehouse.pk
        )
    if 'manager' in fields:
        fields['manager'] = _resolve_manager(
            company=warehouse.company, manager=fields['manager']
        )

    for field, value in fields.items():
        setattr(warehouse, field, value)
    warehouse.save(update_fields=[*fields, 'updated_at'])

    transaction.on_commit(lambda: invalidate_company_reports(warehouse.company_id))
    return warehouse


@transaction.atomic
def delete_warehouse(*, warehouse: Warehouse) -> None:
    """Delete a warehouse that never held any stock.

    A warehouse that appears in the ledger must not disappear -- it would
    rewrite history. Deactivate it instead (``PATCH {"is_active": false}``).
    """
    if selectors.has_movements(warehouse=warehouse):
        raise Conflict({
            'detail': (
                'This warehouse has stock movements and cannot be deleted. '
                'Set is_active=false to retire it instead.'
            )
        })

    company_id = warehouse.company_id
    warehouse.delete()
    transaction.on_commit(lambda: invalidate_company_reports(company_id))

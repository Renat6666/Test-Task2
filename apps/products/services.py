"""Product write operations."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.common.cache import invalidate_company_reports
from apps.common.exceptions import BusinessRuleViolation, Conflict
from apps.products.models import Product


def _assert_sku_is_free(*, company, sku: str, exclude_pk=None) -> None:
    """A SKU may only be used by one live product per company."""
    clash = Product.objects.alive().filter(company=company, sku=sku)
    if exclude_pk is not None:
        clash = clash.exclude(pk=exclude_pk)
    if clash.exists():
        raise BusinessRuleViolation(
            {'sku': [f'A product with SKU "{sku}" already exists.']}
        )


@transaction.atomic
def create_product(
    *,
    company,
    sku: str,
    name: str,
    base_price: Decimal,
    description: str = '',
    min_stock_level: Decimal = Decimal('0'),
) -> Product:
    """Create a product for a company."""
    sku = sku.strip()
    _assert_sku_is_free(company=company, sku=sku)

    product = Product.objects.create(
        company=company,
        sku=sku,
        name=name.strip(),
        description=description,
        base_price=base_price,
        min_stock_level=min_stock_level,
    )
    # The stock value report depends on base_price.
    transaction.on_commit(lambda: invalidate_company_reports(company.pk))
    return product


@transaction.atomic
def update_product(*, product: Product, **fields) -> Product:
    """Update the editable fields of a product."""
    if product.is_deleted:
        raise Conflict({'detail': 'A deleted product cannot be edited; restore it first.'})

    editable = {'sku', 'name', 'description', 'base_price', 'min_stock_level'}
    unknown = set(fields) - editable
    assert not unknown, f'Not editable: {sorted(unknown)}'

    if 'sku' in fields:
        fields['sku'] = fields['sku'].strip()
        _assert_sku_is_free(
            company=product.company, sku=fields['sku'], exclude_pk=product.pk
        )

    for field, value in fields.items():
        setattr(product, field, value)
    product.save(update_fields=[*fields, 'updated_at'])

    transaction.on_commit(lambda: invalidate_company_reports(product.company_id))
    return product


@transaction.atomic
def soft_delete_product(*, product: Product) -> Product:
    """Soft delete a product.

    The row stays in place so past transactions keep resolving; the product
    simply disappears from the catalogue, the stock report and the value
    report.
    """
    if product.is_deleted:
        return product

    product.is_deleted = True
    product.deleted_at = timezone.now()
    product.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    transaction.on_commit(lambda: invalidate_company_reports(product.company_id))
    return product


@transaction.atomic
def restore_product(*, product: Product) -> Product:
    """Undo a soft delete."""
    if not product.is_deleted:
        return product

    _assert_sku_is_free(company=product.company, sku=product.sku, exclude_pk=product.pk)

    product.is_deleted = False
    product.deleted_at = None
    product.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    transaction.on_commit(lambda: invalidate_company_reports(product.company_id))
    return product

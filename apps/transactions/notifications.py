"""Outgoing notifications triggered by stock movements."""

import logging

from django.conf import settings
from django.core.mail import send_mail

from apps.users import selectors as user_selectors

logger = logging.getLogger(__name__)


def send_low_stock_alert(*, product, warehouse, remaining) -> None:
    """Tell the warehouse manager that an article is running out.

    Sent after an ``OUT`` transaction dropped the balance below the product's
    ``min_stock_level``. Called from ``transaction.on_commit`` so an email is
    never sent for a movement that got rolled back.
    """
    recipients = user_selectors.warehouse_alert_recipients(warehouse=warehouse)
    if not recipients:
        logger.warning(
            'Low stock on %s for %s but no alert recipient is configured.',
            warehouse, product.sku,
        )
        return

    try:
        send_mail(
            subject=f'[Inventory] Low stock: {product.sku} on {warehouse.name}',
            message=(
                f'The stock of "{product.name}" (SKU {product.sku}) on warehouse '
                f'"{warehouse.name}" dropped below its minimum level.\n\n'
                f'  Remaining:     {remaining}\n'
                f'  Minimum level: {product.min_stock_level}\n\n'
                'Please restock this article.\n'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
        )
    except Exception:
        # The shipment itself is already committed -- a broken mail server must
        # not turn a valid transaction into a failed request.
        logger.exception('Could not send the low stock alert for %s', product.sku)
        return

    logger.info('Low stock alert for %s sent to %s', product.sku, recipients)

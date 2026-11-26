"""Read access to employees."""

from django.contrib.auth import get_user_model
from django.db.models import QuerySet

User = get_user_model()


def employee_list(*, company) -> QuerySet:
    """Active employees of a company."""
    return (
        User.objects.filter(company=company)
        .select_related('company')
        .order_by('username')
    )


def find_by_email(*, email: str):
    """Return the user owning ``email`` (case insensitive) or ``None``."""
    return User.objects.filter(email__iexact=email.strip()).first()


def find_by_login(*, login: str):
    """Resolve a login that may be either a username or an email address."""
    login = login.strip()
    return (
        User.objects.filter(username=login).first()
        or User.objects.filter(email__iexact=login).first()
    )


def warehouse_alert_recipients(*, warehouse) -> list[str]:
    """Email addresses that should be told the stock of a warehouse is low.

    The warehouse manager first; if no manager is assigned we fall back to the
    staff members of the company so the alert is never silently dropped.
    """
    if warehouse.manager_id and warehouse.manager.email:
        return [warehouse.manager.email]
    return list(
        User.objects.filter(company_id=warehouse.company_id, is_staff=True)
        .exclude(email='')
        .values_list('email', flat=True)
    )

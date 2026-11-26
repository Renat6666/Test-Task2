"""Read access to companies."""

from django.db.models import QuerySet

from apps.companies.models import Company


def company_list(*, company) -> QuerySet[Company]:
    """Companies visible to an employee -- only their own."""
    return Company.objects.filter(pk=company.pk)


def find_by_name(*, name: str) -> Company | None:
    """Return the company with this (case insensitive) name, if any."""
    return Company.objects.filter(name__iexact=name.strip()).first()

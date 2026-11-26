"""Company write operations."""

from apps.companies import selectors
from apps.companies.models import Company


def get_or_create_company(*, name: str) -> Company:
    """Return the company called ``name``, creating it when it is new.

    Registration uses this: the first employee of a company creates it, later
    employees join it by using the same company name. A production system would
    replace the "join by name" part with an invitation flow.
    """
    name = name.strip()
    existing = selectors.find_by_name(name=name)
    if existing is not None:
        return existing
    return Company.objects.create(name=name)


def rename_company(*, company: Company, name: str) -> Company:
    """Rename a company."""
    company.name = name.strip()
    company.full_clean(validate_unique=True)
    company.save(update_fields=['name'])
    return company

"""Permissions shared by the API.

The whole API is multi-tenant: an employee only ever sees the data of the
company they belong to. The queryset filtering lives in the selectors, this
permission only guarantees that a company is present on the request.
"""

from rest_framework.permissions import BasePermission


class IsCompanyEmployee(BasePermission):
    """Allow authenticated users that are attached to a company."""

    message = 'Your account is not attached to a company.'

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, 'company_id', None) is not None
        )

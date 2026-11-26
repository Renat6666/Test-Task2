"""Domain exceptions and the DRF exception handler.

Service functions raise these; because they derive from DRF's ``APIException``
the view layer needs no translation step and stays free of error handling.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.views import exception_handler as drf_exception_handler


class BusinessRuleViolation(DRFValidationError):
    """A request was well formed but violates a business rule (HTTP 400)."""


class InsufficientStock(BusinessRuleViolation):
    """Not enough stock on the source warehouse to cover the movement."""

    def __init__(self, *, product, warehouse, requested, available):
        super().__init__({
            'quantity': [
                f'Insufficient stock for "{product}" on warehouse '
                f'"{warehouse}": requested {requested}, available {available}.'
            ],
            'available_quantity': str(available),
        })


class Conflict(DRFValidationError):
    """The object cannot be changed in its current state."""

    status_code = status.HTTP_409_CONFLICT


def api_exception_handler(exc, context):
    """Translate non-DRF errors into regular API error responses."""
    if isinstance(exc, DjangoValidationError):
        exc = DRFValidationError(exc.message_dict if hasattr(exc, 'message_dict') else exc.messages)
    elif isinstance(exc, ProtectedError):
        exc = Conflict({
            'detail': 'This object is referenced by other records and cannot be deleted.'
        })
    return drf_exception_handler(exc, context)

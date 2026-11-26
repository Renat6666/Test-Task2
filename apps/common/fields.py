"""Shared decimal field definitions.

Quantities and money are decimals everywhere in this project; the output fields
below are reused by every ORM expression so that annotations, model columns and
serializers agree on precision.
"""

from decimal import Decimal

from django.db.models import DecimalField, Value

QUANTITY_MAX_DIGITS = 14
QUANTITY_DECIMAL_PLACES = 3

MONEY_MAX_DIGITS = 12
MONEY_DECIMAL_PLACES = 2

#: Room for the product of a quantity and a price.
VALUE_MAX_DIGITS = 26
VALUE_DECIMAL_PLACES = 5

#: Output field for aggregated quantities (sum of ledger entries).
QUANTITY_OUTPUT_FIELD = DecimalField(
    max_digits=QUANTITY_MAX_DIGITS,
    decimal_places=QUANTITY_DECIMAL_PLACES,
)

#: Output field for ``quantity * base_price`` style expressions.
VALUE_OUTPUT_FIELD = DecimalField(
    max_digits=VALUE_MAX_DIGITS,
    decimal_places=VALUE_DECIMAL_PLACES,
)

ZERO_QUANTITY = Value(Decimal('0'), output_field=QUANTITY_OUTPUT_FIELD)
ZERO_VALUE = Value(Decimal('0'), output_field=VALUE_OUTPUT_FIELD)


def as_quantity(value) -> Decimal:
    """Normalise ``value`` to a quantity shaped ``Decimal``."""
    return Decimal(value).quantize(Decimal('0.001'))


def as_money(value) -> Decimal:
    """Normalise ``value`` to a money shaped ``Decimal``."""
    return Decimal(value).quantize(Decimal('0.01'))

"""Rate limiting for stock movements.

The counters live in Redis (the default Django cache), so the limit holds
across every application process.
"""

from django.core.cache import cache
from rest_framework.throttling import UserRateThrottle


class TransactionCreateThrottle(UserRateThrottle):
    """At most 50 new transactions per employee per minute.

    The rate itself is configured as ``DEFAULT_THROTTLE_RATES['transaction_create']``.
    """

    scope = 'transaction_create'
    cache = cache

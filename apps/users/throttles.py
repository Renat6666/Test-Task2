"""Throttles protecting the credential endpoints (counters live in Redis)."""

from rest_framework.throttling import AnonRateThrottle


class AuthThrottle(AnonRateThrottle):
    """Rate limit login / register / password reset attempts per IP."""

    scope = 'auth'

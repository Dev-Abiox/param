"""
Resilient throttle classes that fail-open when the cache backend is unavailable.

DRF's built-in throttle classes crash with a 500 when Redis is down because
cache.get()/set() raises ConnectionError.  These wrappers catch cache
exceptions and allow the request through, so a Redis outage degrades
rate-limiting but does not break the API.
"""

import logging

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

logger = logging.getLogger(__name__)


class ResilientAnonRateThrottle(AnonRateThrottle):
    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            logger.warning("throttle_cache_error: AnonRateThrottle bypassed")
            return True


class ResilientUserRateThrottle(UserRateThrottle):
    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            logger.warning("throttle_cache_error: UserRateThrottle bypassed")
            return True

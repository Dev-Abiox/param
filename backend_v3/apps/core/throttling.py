"""
Resilient throttle classes that fail-open when the cache backend is unavailable.

DRF's built-in throttle classes crash with a 500 when Redis is down because
cache.get()/set() raises ConnectionError.  These wrappers catch cache
exceptions and allow the request through, so a Redis outage degrades
rate-limiting but does not break the API.

Auth-critical throttles (login, MFA, password reset) fail *closed* instead:
a Redis outage must not allow unlimited brute-force attempts.
"""

import logging

import jwt
from django.conf import settings
from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle, UserRateThrottle

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


class _FailClosedMixin:
    """Deny the request when the cache backend is unreachable.

    Auth-critical endpoints (login, MFA, password reset) must never allow
    unlimited attempts just because Redis is temporarily down.
    """

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            logger.error("throttle_cache_error: %s denied (fail-closed)", self.__class__.__name__)
            return False


class LoginRateThrottle(_FailClosedMixin, SimpleRateThrottle):
    scope = 'login'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }


class MFATOTPThrottle(_FailClosedMixin, SimpleRateThrottle):
    """5 attempts per 5-minute window, keyed on IP + user identifier.

    Extracts the user ID from the mfa_pending_token JWT so each user's
    counter is separate even behind a shared IP (e.g. NAT).
    """
    scope = 'mfa_verify'
    rate = '5/min'
    TIMER_SECONDS = 300  # 5-minute window

    def parse_rate(self, rate):
        num, _period = super().parse_rate(rate)
        return (num, self.TIMER_SECONDS)

    def get_cache_key(self, request, view):
        user_id = ''
        pending_token = (request.data or {}).get('mfa_pending_token', '')
        if pending_token:
            try:
                payload = jwt.decode(
                    pending_token,
                    settings.JWT_SECRET_KEY,
                    algorithms=[settings.JWT_ALGORITHM],
                    options={'verify_exp': False},
                )
                user_id = payload.get('sub', '')
            except Exception:
                pass
        ident = f"{self.get_ident(request)}-{user_id}"
        return self.cache_format % {
            'scope': self.scope,
            'ident': ident,
        }


class MFAResendThrottle(_FailClosedMixin, SimpleRateThrottle):
    """3 resends per 5-minute window per IP."""
    scope = 'mfa_resend'
    rate = '3/min'
    TIMER_SECONDS = 300  # 5-minute window

    def parse_rate(self, rate):
        num, _period = super().parse_rate(rate)
        return (num, self.TIMER_SECONDS)

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }


class PasswordResetRateThrottle(_FailClosedMixin, SimpleRateThrottle):
    """Rate limit password reset requests (both initiation and consumption)."""
    scope = 'password_reset'

    def get_cache_key(self, request, view):
        return self.cache_format % {
            'scope': self.scope,
            'ident': self.get_ident(request),
        }

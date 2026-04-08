"""
Lightweight Redis-backed circuit breaker for external service calls.

States:
  CLOSED  — requests pass through normally; failures are counted.
  OPEN    — requests are immediately rejected (fail fast).
  HALF_OPEN — a single probe request is allowed through to test recovery.

Transition rules:
  CLOSED → OPEN    when failure_count >= failure_threshold within the window.
  OPEN → HALF_OPEN after recovery_timeout seconds.
  HALF_OPEN → CLOSED on success; HALF_OPEN → OPEN on failure.
"""

import logging
import time

from django.core.cache import cache

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open and rejecting calls."""
    pass


class CircuitBreaker:
    """
    Redis-backed circuit breaker.

    Usage::

        cb = CircuitBreaker('razorpay', failure_threshold=5, recovery_timeout=60)
        try:
            cb.before_call()
            result = make_external_call()
            cb.on_success()
        except CircuitOpenError:
            # circuit is open — skip the call
            pass
        except SomeExternalError as e:
            cb.on_failure()
            raise
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        window: int = 120,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.window = window

        self._fail_count_key = f'cb:{name}:fail_count'
        self._open_until_key = f'cb:{name}:open_until'

    def _get_state(self) -> str:
        try:
            open_until = cache.get(self._open_until_key)
            if open_until:
                if time.time() < float(open_until):
                    return 'OPEN'
                return 'HALF_OPEN'
        except Exception:
            pass
        return 'CLOSED'

    def before_call(self) -> None:
        """Check circuit state before making an external call."""
        state = self._get_state()
        if state == 'OPEN':
            raise CircuitOpenError(
                f'Circuit breaker "{self.name}" is OPEN — '
                f'external service calls are temporarily suspended.'
            )
        # HALF_OPEN and CLOSED both allow the call through

    def on_success(self) -> None:
        """Record a successful call — resets failure count, closes circuit."""
        try:
            cache.delete(self._fail_count_key)
            cache.delete(self._open_until_key)
        except Exception:
            pass

    def on_failure(self) -> None:
        """Record a failed call — may trip the circuit to OPEN."""
        try:
            fail_count = cache.get(self._fail_count_key, 0)
            fail_count = int(fail_count) + 1
            cache.set(self._fail_count_key, fail_count, timeout=self.window)

            if fail_count >= self.failure_threshold:
                open_until = time.time() + self.recovery_timeout
                cache.set(self._open_until_key, str(open_until), timeout=self.recovery_timeout + 10)
                logger.warning(
                    'circuit_breaker_tripped',
                    name=self.name,
                    fail_count=fail_count,
                    recovery_seconds=self.recovery_timeout,
                )
        except Exception:
            pass  # circuit breaker is best-effort; don't block the caller

    def get_status(self) -> dict:
        """Return the current circuit breaker state for monitoring."""
        try:
            fail_count = int(cache.get(self._fail_count_key, 0))
        except Exception:
            fail_count = 0

        state = self._get_state()
        return {
            'name': self.name,
            'state': state,
            'failure_count': fail_count,
            'failure_threshold': self.failure_threshold,
            'recovery_timeout': self.recovery_timeout,
        }

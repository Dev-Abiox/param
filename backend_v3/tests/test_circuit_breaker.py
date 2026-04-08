"""
Tests for the circuit breaker module.
"""

import time
from unittest.mock import patch

from apps.billing.circuit_breaker import CircuitBreaker, CircuitOpenError


class TestCircuitBreaker:

    def _make_cb(self, **kwargs):
        defaults = dict(name='test', failure_threshold=3, recovery_timeout=5, window=60)
        defaults.update(kwargs)
        return CircuitBreaker(**defaults)

    @patch('apps.billing.circuit_breaker.cache')
    def test_starts_closed(self, mock_cache):
        mock_cache.get.return_value = None
        cb = self._make_cb()
        # Should not raise
        cb.before_call()

    @patch('apps.billing.circuit_breaker.cache')
    def test_opens_after_threshold_failures(self, mock_cache):
        stored = {}

        def mock_get(key, default=None):
            return stored.get(key, default)

        def mock_set(key, value, timeout=None):
            stored[key] = value

        mock_cache.get.side_effect = mock_get
        mock_cache.set.side_effect = mock_set

        cb = self._make_cb(failure_threshold=3)

        # Record 3 failures
        cb.on_failure()
        cb.on_failure()
        cb.on_failure()

        # Circuit should now be OPEN
        assert cb.get_status()['state'] == 'OPEN'

    @patch('apps.billing.circuit_breaker.cache')
    def test_open_circuit_raises(self, mock_cache):
        """When circuit is open, before_call raises CircuitOpenError."""
        # Simulate an open circuit (open_until is in the future)
        def mock_get(key, default=None):
            if 'open_until' in key:
                return str(time.time() + 60)
            return default

        mock_cache.get.side_effect = mock_get

        cb = self._make_cb()
        try:
            cb.before_call()
            assert False, "Should have raised CircuitOpenError"
        except CircuitOpenError:
            pass

    @patch('apps.billing.circuit_breaker.cache')
    def test_half_open_after_recovery(self, mock_cache):
        """After recovery_timeout, circuit transitions to HALF_OPEN."""
        def mock_get(key, default=None):
            if 'open_until' in key:
                return str(time.time() - 1)  # expired
            return default

        mock_cache.get.side_effect = mock_get

        cb = self._make_cb()
        # Should not raise (HALF_OPEN allows calls)
        cb.before_call()
        assert cb.get_status()['state'] == 'HALF_OPEN'

    @patch('apps.billing.circuit_breaker.cache')
    def test_success_resets_circuit(self, mock_cache):
        cb = self._make_cb()
        cb.on_success()
        mock_cache.delete.assert_called()

    @patch('apps.billing.circuit_breaker.cache')
    def test_cache_failure_is_graceful(self, mock_cache):
        """Circuit breaker should never crash the caller."""
        mock_cache.get.side_effect = Exception("Redis down")

        cb = self._make_cb()
        # Should not raise even with cache failures
        cb.before_call()
        cb.on_failure()
        cb.on_success()
        status = cb.get_status()
        assert status['failure_count'] == 0  # couldn't read from cache

"""
Tests for per-org rate limiting middleware.
"""

from unittest.mock import MagicMock, PropertyMock, patch

from django.test import RequestFactory


def _make_request(path='/api/screening/predict'):
    factory = RequestFactory()
    request = factory.get(path)
    org = MagicMock()
    org.id = 'org-123'
    org.schema_name = 'test_org'
    request.tenant = org
    return request


class TestOrgRateLimitMiddleware:

    def _make_mw(self, get_response=None, limit=5):
        from apps.billing.middleware import OrgRateLimitMiddleware
        get_response = get_response or MagicMock(return_value=MagicMock(status_code=200))
        mw = OrgRateLimitMiddleware(get_response)
        mw.limit = limit
        return mw, get_response

    @patch('apps.billing.middleware.cache')
    def test_allows_requests_under_limit(self, mock_cache):
        mock_cache.get.return_value = 3
        mw, get_response = self._make_mw(limit=5)
        request = _make_request()

        response = mw(request)

        assert response.status_code == 200
        get_response.assert_called_once()

    @patch('apps.billing.middleware.cache')
    def test_blocks_requests_at_limit(self, mock_cache):
        # cache.incr now returns the post-increment value; 6 > 5 → block
        mock_cache.incr.return_value = 6
        mw, get_response = self._make_mw(limit=5)
        request = _make_request()

        response = mw(request)

        assert response.status_code == 429
        get_response.assert_not_called()

    @patch('apps.billing.middleware.cache')
    def test_passes_through_non_screening_paths(self, mock_cache):
        mw, get_response = self._make_mw(limit=0)
        request = _make_request(path='/api/auth/login')

        response = mw(request)

        assert response.status_code == 200
        mock_cache.get.assert_not_called()

    @patch('apps.billing.middleware.cache')
    def test_passes_through_public_tenant(self, mock_cache):
        mw, get_response = self._make_mw(limit=0)
        request = _make_request()
        request.tenant.schema_name = 'public'

        response = mw(request)

        assert response.status_code == 200
        mock_cache.get.assert_not_called()

    @patch('apps.billing.middleware.cache')
    def test_redis_failure_allows_request(self, mock_cache):
        """If Redis is down, fail open (this middleware is a soft DoS guard,
        PlanLimitMiddleware is the source of truth for hard quota enforcement)."""
        mock_cache.incr.side_effect = Exception("Redis down")
        mw, get_response = self._make_mw(limit=1)
        request = _make_request()

        response = mw(request)

        assert response.status_code == 200
        get_response.assert_called_once()

    @patch('apps.billing.middleware.cache')
    def test_increments_counter_atomically(self, mock_cache):
        # cache.incr returns 3 (atomic post-increment) and we don't separately
        # call cache.set anymore.
        mock_cache.incr.return_value = 3
        mw, _ = self._make_mw(limit=5)
        request = _make_request()

        mw(request)

        mock_cache.incr.assert_called_with('org_ratelimit:org-123')
        # cache.set is never called on the happy path with the new atomic flow
        mock_cache.set.assert_not_called()

    @patch('apps.billing.middleware.cache')
    def test_initialises_counter_when_missing(self, mock_cache):
        """First request for an org: cache.incr raises ValueError, fall back to add+incr."""
        mock_cache.incr.side_effect = [ValueError("no key"), 1]
        mw, _ = self._make_mw(limit=5)
        request = _make_request()

        response = mw(request)

        assert response.status_code == 200
        # cache.add called to seed the key with 0
        mock_cache.add.assert_called_once_with('org_ratelimit:org-123', 0, timeout=60)
        assert mock_cache.incr.call_count == 2

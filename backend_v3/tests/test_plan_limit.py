"""
Tests for PlanLimitMiddleware.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache
from django.http import JsonResponse
from django.test import RequestFactory


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear Django cache before each test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def middleware():
    from apps.billing.middleware import PlanLimitMiddleware
    inner = MagicMock(return_value='ok')
    return PlanLimitMiddleware(inner)


class TestPlanLimitMiddleware:

    def test_post_predict_under_limit_passes(self, rf, middleware):
        """POST to /api/screening/predict below limit should pass through."""
        request = rf.post('/api/screening/predict')
        org = MagicMock()
        org.schema_name = 'clinic_1'
        org.id = 'org-1'
        request.tenant = org

        with patch.object(middleware, '_is_over_limit', return_value=False):
            result = middleware(request)

        assert result == 'ok'

    def test_post_predict_over_limit_returns_402(self, rf, middleware):
        """POST to /api/screening/predict at limit should return 402."""
        request = rf.post('/api/screening/predict')
        org = MagicMock()
        org.schema_name = 'clinic_1'
        org.id = 'org-1'
        request.tenant = org

        with patch.object(middleware, '_is_over_limit', return_value=True):
            result = middleware(request)

        assert isinstance(result, JsonResponse)
        assert result.status_code == 402

    def test_get_request_always_passes(self, rf, middleware):
        """GET requests should always pass through, even to predict endpoint."""
        request = rf.get('/api/screening/predict')
        org = MagicMock()
        org.schema_name = 'clinic_1'
        request.tenant = org

        result = middleware(request)
        assert result == 'ok'

    def test_non_predict_post_passes(self, rf, middleware):
        """POST to non-predict paths should pass through."""
        request = rf.post('/api/screening/queue')
        org = MagicMock()
        org.schema_name = 'clinic_1'
        request.tenant = org

        result = middleware(request)
        assert result == 'ok'

    def test_trailing_slash_normalization(self, rf, middleware):
        """Path with trailing slash should still be matched."""
        request = rf.post('/api/screening/predict/')
        org = MagicMock()
        org.schema_name = 'clinic_1'
        org.id = 'org-1'
        request.tenant = org

        with patch.object(middleware, '_is_over_limit', return_value=True):
            result = middleware(request)

        assert isinstance(result, JsonResponse)
        assert result.status_code == 402

    def test_case_insensitive_path(self, rf, middleware):
        """Uppercase path should still be matched."""
        request = rf.post('/api/Screening/Predict')
        request.path = '/api/Screening/Predict'
        org = MagicMock()
        org.schema_name = 'clinic_1'
        org.id = 'org-1'
        request.tenant = org

        with patch.object(middleware, '_is_over_limit', return_value=True):
            result = middleware(request)

        assert isinstance(result, JsonResponse)
        assert result.status_code == 402

    def test_v1_predict_path_also_checked(self, rf, middleware):
        """POST to /api/v1/screening/predict should also be checked."""
        request = rf.post('/api/v1/screening/predict')
        org = MagicMock()
        org.schema_name = 'clinic_1'
        org.id = 'org-1'
        request.tenant = org

        with patch.object(middleware, '_is_over_limit', return_value=True):
            result = middleware(request)

        assert isinstance(result, JsonResponse)
        assert result.status_code == 402

    def test_public_schema_not_checked(self, rf, middleware):
        """Public schema tenants should not be rate-limited."""
        request = rf.post('/api/screening/predict')
        org = MagicMock()
        org.schema_name = 'public'
        request.tenant = org

        result = middleware(request)
        assert result == 'ok'

    def test_no_tenant_passes_through(self, rf, middleware):
        """Requests without a tenant should pass through."""
        request = rf.post('/api/screening/predict')
        request.tenant = None

        result = middleware(request)
        assert result == 'ok'


class TestIsOverLimit:

    def test_db_error_fails_closed(self, rf):
        """DB errors should fail closed (return True) and NOT cache."""
        from apps.billing.middleware import PlanLimitMiddleware

        mw = PlanLimitMiddleware(MagicMock())
        org = MagicMock()
        org.id = 'org-db-err'

        with patch('apps.billing.middleware.TenantSubscription') as MockSub:
            MockSub.objects.select_related.return_value.get.side_effect = RuntimeError('db down')

            result = mw._is_over_limit(org)

        assert result is True
        # Should NOT be cached
        assert cache.get(f'plan_limit_over:{org.id}') is None

    def test_cache_hit_returns_cached_value(self, rf):
        """Cached results should be returned without DB hit."""
        from apps.billing.middleware import PlanLimitMiddleware

        mw = PlanLimitMiddleware(MagicMock())
        org = MagicMock()
        org.id = 'org-cached'

        cache.set(f'plan_limit_over:{org.id}', True, timeout=60)

        with patch('apps.billing.middleware.TenantSubscription') as MockSub:
            result = mw._is_over_limit(org)

        assert result is True
        MockSub.objects.select_related.assert_not_called()

    def test_no_subscription_returns_false(self, rf):
        """Missing subscription should return False (no limit to enforce)."""
        from apps.billing.middleware import PlanLimitMiddleware
        from apps.billing.models import TenantSubscription

        mw = PlanLimitMiddleware(MagicMock())
        org = MagicMock()
        org.id = 'org-no-sub'

        with patch('apps.billing.middleware.TenantSubscription') as MockSub:
            MockSub.DoesNotExist = TenantSubscription.DoesNotExist
            MockSub.objects.select_related.return_value.get.side_effect = TenantSubscription.DoesNotExist

            result = mw._is_over_limit(org)

        assert result is False

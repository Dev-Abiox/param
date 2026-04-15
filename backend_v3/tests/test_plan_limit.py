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

        with patch.object(middleware, '_is_blocked', return_value=(False, '')):
            result = middleware(request)

        assert result == 'ok'

    def test_post_predict_over_limit_returns_402(self, rf, middleware):
        """POST to /api/screening/predict at limit should return 402."""
        request = rf.post('/api/screening/predict')
        org = MagicMock()
        org.schema_name = 'clinic_1'
        org.id = 'org-1'
        request.tenant = org

        with patch.object(middleware, '_is_blocked', return_value=(True, 'Monthly screening limit reached. Please upgrade your plan.')):
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

        with patch.object(middleware, '_is_blocked', return_value=(True, 'limit')):
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

        with patch.object(middleware, '_is_blocked', return_value=(True, 'limit')):
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

        with patch.object(middleware, '_is_blocked', return_value=(True, 'limit')):
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


class TestIsBlocked:

    def test_db_error_fails_open(self, rf):
        """
        DB errors must fail OPEN (allow the request through) and NOT cache.

        The historical behavior was fail-closed, which meant one Redis/DB blip
        would 402 every paying customer. The new contract: let the request
        through, emit a warning + bump BILLING_PLAN_LIMIT_FAIL_OPEN so the
        incident is visible in Prometheus. The billing.increment_usage task
        reconciles actual quota afterwards.
        """
        from apps.billing.middleware import PlanLimitMiddleware
        from apps.billing.models import TenantSubscription

        mw = PlanLimitMiddleware(MagicMock())
        org = MagicMock()
        org.id = 'org-db-err'

        with patch('apps.billing.models.TenantSubscription') as MockSub, \
             patch('apps.core.metrics.BILLING_PLAN_LIMIT_FAIL_OPEN') as MockCounter:
            MockSub.DoesNotExist = TenantSubscription.DoesNotExist
            MockSub.objects.select_related.return_value.get.side_effect = RuntimeError('db down')

            result = mw._is_blocked(org)

        assert result == (False, '')
        # Counter must fire so ops see the fail-open in Grafana.
        MockCounter.inc.assert_called_once()
        # Must NOT be cached — a transient error should not persist.
        assert cache.get(f'plan_limit_over:{org.id}') is None

    def test_cache_get_error_fails_open(self, rf):
        """
        Redis unreachable on the cache.get path must also fail OPEN rather than
        crashing the request with a 500 from an uncaught exception.
        """
        from apps.billing.middleware import PlanLimitMiddleware

        mw = PlanLimitMiddleware(MagicMock())
        org = MagicMock()
        org.id = 'org-cache-err'

        with patch('apps.billing.middleware.cache') as MockCache, \
             patch('apps.core.metrics.BILLING_PLAN_LIMIT_FAIL_OPEN') as MockCounter:
            MockCache.get.side_effect = ConnectionError('redis down')

            result = mw._is_blocked(org)

        assert result == (False, '')
        MockCounter.inc.assert_called_once()

    def test_cache_set_error_still_returns_db_result(self, rf):
        """
        If cache.set fails (Redis partial outage), the DB-derived result must
        still be returned — the next request will recompute it.
        """
        from apps.billing.middleware import PlanLimitMiddleware

        mw = PlanLimitMiddleware(MagicMock())
        org = MagicMock()
        org.id = 'org-cache-set-err'

        sub = MagicMock()
        sub.status = 'ACTIVE'
        sub.plan.monthly_limit = 100
        sub.current_period_count = 5  # under limit

        with patch('apps.billing.models.TenantSubscription') as MockSub, \
             patch('apps.billing.middleware.cache') as MockCache:
            MockSub.objects.select_related.return_value.get.return_value = sub
            MockSub.Status.EXPIRED = 'EXPIRED'
            MockSub.Status.CANCELLED = 'CANCELLED'
            MockSub.Status.TRIAL = 'TRIAL'
            MockCache.get.return_value = None
            MockCache.set.side_effect = ConnectionError('redis down on write')

            result = mw._is_blocked(org)

        assert result == (False, '')

    def test_cache_hit_returns_cached_value(self, rf):
        """Cached results should be returned without DB hit."""
        from apps.billing.middleware import PlanLimitMiddleware

        mw = PlanLimitMiddleware(MagicMock())
        org = MagicMock()
        org.id = 'org-cached'

        cache.set(f'plan_limit_over:{org.id}', (True, 'limit'), timeout=60)

        with patch('apps.billing.models.TenantSubscription') as MockSub:
            result = mw._is_blocked(org)

        assert result[0] is True
        MockSub.objects.select_related.assert_not_called()

    def test_no_subscription_returns_false(self, rf):
        """Missing subscription should return not-blocked."""
        from apps.billing.middleware import PlanLimitMiddleware
        from apps.billing.models import TenantSubscription

        mw = PlanLimitMiddleware(MagicMock())
        org = MagicMock()
        org.id = 'org-no-sub'

        with patch('apps.billing.models.TenantSubscription') as MockSub:
            MockSub.DoesNotExist = TenantSubscription.DoesNotExist
            MockSub.objects.select_related.return_value.get.side_effect = TenantSubscription.DoesNotExist

            result = mw._is_blocked(org)

        assert result[0] is False

"""
Tests for billing Celery tasks: increment_usage and compute_monthly_rollups.
"""

import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock, patch, call

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


# ── increment_usage ──────────────────────────────────────────────────────────

class TestIncrementUsage:

    def test_increments_count_and_busts_cache(self):
        """Should atomically increment current_period_count and bust plan-limit cache."""
        from apps.billing.tasks import increment_usage

        org_id = str(uuid.uuid4())
        screening_id = str(uuid.uuid4())

        # Seed the plan-limit cache so we can verify it gets busted
        cache.set(f'plan_limit_over:{org_id}', False, timeout=60)

        mock_sub = MagicMock()
        mock_sub.current_period_count = 5
        mock_sub.plan.monthly_limit = 100

        with patch('apps.billing.models.TenantSubscription') as MockSub:
            MockSub.objects.filter.return_value.update.return_value = 1
            MockSub.objects.select_related.return_value.get.return_value = mock_sub
            MockSub.DoesNotExist = Exception

            increment_usage(org_id, screening_id)

        # Verify atomic update was called
        MockSub.objects.filter.assert_called_once_with(organization_id=org_id)
        # Verify plan-limit cache was busted
        assert cache.get(f'plan_limit_over:{org_id}') is None

    def test_deduplication_prevents_double_increment(self):
        """Same screening_id should be skipped on second call."""
        from apps.billing.tasks import increment_usage

        org_id = str(uuid.uuid4())
        screening_id = str(uuid.uuid4())

        with patch('apps.billing.models.TenantSubscription') as MockSub:
            mock_sub = MagicMock()
            mock_sub.current_period_count = 5
            mock_sub.plan.monthly_limit = 100
            MockSub.objects.filter.return_value.update.return_value = 1
            MockSub.objects.select_related.return_value.get.return_value = mock_sub
            MockSub.DoesNotExist = Exception

            # First call — should proceed
            increment_usage(org_id, screening_id)
            assert MockSub.objects.filter.return_value.update.call_count == 1

            # Second call — should skip (dedup key already in cache)
            increment_usage(org_id, screening_id)
            assert MockSub.objects.filter.return_value.update.call_count == 1  # no second update

    def test_empty_org_id_returns_early(self):
        """Empty org_id should short-circuit."""
        from apps.billing.tasks import increment_usage

        with patch('apps.billing.models.TenantSubscription') as MockSub:
            increment_usage('', str(uuid.uuid4()))
            increment_usage(None, str(uuid.uuid4()))

        MockSub.objects.filter.assert_not_called()

    def test_empty_screening_id_returns_early(self):
        """Empty screening_id should short-circuit."""
        from apps.billing.tasks import increment_usage

        with patch('apps.billing.models.TenantSubscription') as MockSub:
            increment_usage(str(uuid.uuid4()), '')

        MockSub.objects.filter.assert_not_called()

    def test_no_subscription_logs_warning(self):
        """If no TenantSubscription matches, update returns 0."""
        from apps.billing.tasks import increment_usage

        org_id = str(uuid.uuid4())
        screening_id = str(uuid.uuid4())

        with patch('apps.billing.models.TenantSubscription') as MockSub:
            MockSub.objects.filter.return_value.update.return_value = 0

            increment_usage(org_id, screening_id)

        # No cache bust attempted for non-existent subscription
        assert cache.get(f'plan_limit_over:{org_id}') is None

    def test_threshold_80_fires_alert(self):
        """When count crosses 80% threshold, send_usage_alert should be fired."""
        from apps.billing.tasks import increment_usage

        org_id = str(uuid.uuid4())
        screening_id = str(uuid.uuid4())

        mock_sub = MagicMock()
        mock_sub.current_period_count = 80  # Just crossed 80% of 100
        mock_sub.plan.monthly_limit = 100

        with patch('apps.billing.models.TenantSubscription') as MockSub, \
             patch('apps.billing.tasks.send_usage_alert') as mock_alert:
            MockSub.objects.filter.return_value.update.return_value = 1
            MockSub.objects.select_related.return_value.get.return_value = mock_sub
            MockSub.DoesNotExist = Exception

            increment_usage(org_id, screening_id)

        mock_alert.delay.assert_called_once_with(
            org_id=org_id,
            current_count=80,
            limit=100,
            threshold_pct=80,
        )

    def test_threshold_not_fired_when_already_past(self):
        """If count is well past a threshold, no alert should fire."""
        from apps.billing.tasks import increment_usage

        org_id = str(uuid.uuid4())
        screening_id = str(uuid.uuid4())

        mock_sub = MagicMock()
        mock_sub.current_period_count = 85  # prev=84, no threshold boundary
        mock_sub.plan.monthly_limit = 100

        with patch('apps.billing.models.TenantSubscription') as MockSub, \
             patch('apps.billing.tasks.send_usage_alert') as mock_alert:
            MockSub.objects.filter.return_value.update.return_value = 1
            MockSub.objects.select_related.return_value.get.return_value = mock_sub
            MockSub.DoesNotExist = Exception

            increment_usage(org_id, screening_id)

        mock_alert.delay.assert_not_called()

    def test_unlimited_plan_no_alert(self):
        """Plans with monthly_limit <= 0 should never fire alerts."""
        from apps.billing.tasks import increment_usage

        org_id = str(uuid.uuid4())
        screening_id = str(uuid.uuid4())

        mock_sub = MagicMock()
        mock_sub.current_period_count = 99999
        mock_sub.plan.monthly_limit = -1  # unlimited

        with patch('apps.billing.models.TenantSubscription') as MockSub, \
             patch('apps.billing.tasks.send_usage_alert') as mock_alert:
            MockSub.objects.filter.return_value.update.return_value = 1
            MockSub.objects.select_related.return_value.get.return_value = mock_sub
            MockSub.DoesNotExist = Exception

            increment_usage(org_id, screening_id)

        mock_alert.delay.assert_not_called()


# ── compute_monthly_rollups ──────────────────────────────────────────────────

class TestComputeMonthlyRollups:

    def test_archives_usage_and_resets_counter(self):
        """Should create UsageRecord and reset current_period_count to 0."""
        from apps.billing.tasks import compute_monthly_rollups

        sub_id = uuid.uuid4()
        mock_sub = MagicMock()
        mock_sub.id = sub_id
        mock_sub.organization_id = str(uuid.uuid4())
        mock_sub.organization = MagicMock()
        mock_sub.current_period_count = 42

        with patch('apps.billing.models.TenantSubscription') as MockSub, \
             patch('apps.billing.models.UsageRecord') as MockUsage, \
             patch('django.db.transaction') as MockTx:
            MockSub.objects.values_list.return_value = [sub_id]
            MockSub.objects.select_for_update.return_value.select_related.return_value.get.return_value = mock_sub
            MockTx.atomic.return_value.__enter__ = MagicMock(return_value=None)
            MockTx.atomic.return_value.__exit__ = MagicMock(return_value=False)

            result = compute_monthly_rollups()

        assert result == 1
        MockUsage.objects.update_or_create.assert_called_once()
        assert mock_sub.current_period_count == 0
        mock_sub.save.assert_called_once()

    def test_lock_prevents_duplicate_execution(self):
        """Second concurrent call should be blocked by the distributed lock."""
        from apps.billing.tasks import compute_monthly_rollups

        # Pre-set the lock key
        lock_key = f'billing_rollup_lock:{date.today().isoformat()}'
        cache.set(lock_key, '1', timeout=3600)

        with patch('apps.billing.models.TenantSubscription') as MockSub:
            result = compute_monthly_rollups()

        assert result == 0
        MockSub.objects.values_list.assert_not_called()

    def test_individual_sub_failure_does_not_halt_others(self):
        """If one subscription rollup fails, the rest should still proceed."""
        from apps.billing.tasks import compute_monthly_rollups

        sub_id_1 = uuid.uuid4()
        sub_id_2 = uuid.uuid4()

        mock_sub_2 = MagicMock()
        mock_sub_2.id = sub_id_2
        mock_sub_2.organization_id = str(uuid.uuid4())
        mock_sub_2.organization = MagicMock()
        mock_sub_2.current_period_count = 10

        with patch('apps.billing.models.TenantSubscription') as MockSub, \
             patch('apps.billing.models.UsageRecord') as MockUsage, \
             patch('django.db.transaction') as MockTx:
            MockSub.objects.values_list.return_value = [sub_id_1, sub_id_2]

            # First sub raises, second succeeds
            def get_side_effect(id):
                if id == sub_id_1:
                    raise RuntimeError('db error')
                return mock_sub_2

            MockSub.objects.select_for_update.return_value.select_related.return_value.get.side_effect = \
                lambda id: get_side_effect(id)
            MockTx.atomic.return_value.__enter__ = MagicMock(return_value=None)
            MockTx.atomic.return_value.__exit__ = MagicMock(return_value=False)

            result = compute_monthly_rollups()

        # Only 1 of 2 succeeded
        assert result == 1


# ── trigger_webhook ──────────────────────────────────────────────────────────

class TestTriggerWebhook:

    def test_fires_for_matching_events(self):
        """Should fire deliver_webhook for endpoints subscribed to the event."""
        from apps.billing.tasks import trigger_webhook

        org = MagicMock()
        endpoint = MagicMock()
        endpoint.id = uuid.uuid4()
        endpoint.events = ['screening.completed', 'consent.revoked']

        with patch('apps.billing.models.WebhookEndpoint') as MockWH, \
             patch('apps.billing.tasks.deliver_webhook') as mock_deliver:
            MockWH.objects.filter.return_value = [endpoint]

            trigger_webhook(org, 'screening.completed', {'id': '123'})

        mock_deliver.delay.assert_called_once_with(
            webhook_endpoint_id=str(endpoint.id),
            event_name='screening.completed',
            payload={'id': '123'},
        )

    def test_skips_non_matching_events(self):
        """Should not fire for endpoints not subscribed to the event."""
        from apps.billing.tasks import trigger_webhook

        org = MagicMock()
        endpoint = MagicMock()
        endpoint.id = uuid.uuid4()
        endpoint.events = ['consent.revoked']  # doesn't include screening.completed

        with patch('apps.billing.models.WebhookEndpoint') as MockWH, \
             patch('apps.billing.tasks.deliver_webhook') as mock_deliver:
            MockWH.objects.filter.return_value = [endpoint]

            trigger_webhook(org, 'screening.completed', {'id': '123'})

        mock_deliver.delay.assert_not_called()

    def test_no_endpoints_does_nothing(self):
        """No active endpoints should result in no webhook deliveries."""
        from apps.billing.tasks import trigger_webhook

        org = MagicMock()

        with patch('apps.billing.models.WebhookEndpoint') as MockWH, \
             patch('apps.billing.tasks.deliver_webhook') as mock_deliver:
            MockWH.objects.filter.return_value = []

            trigger_webhook(org, 'screening.completed', {'id': '123'})

        mock_deliver.delay.assert_not_called()

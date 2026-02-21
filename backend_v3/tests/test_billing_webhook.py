"""
Tests for the billing webhook handler (WebhookView).
"""

import json
import sys
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIRequestFactory


@pytest.fixture
def api_rf():
    return APIRequestFactory()


@pytest.fixture
def mock_razorpay():
    """Fake razorpay module injected into sys.modules so the local import succeeds."""
    mod = MagicMock()
    # By default verify_webhook_signature succeeds (no exception).
    mod.Client.return_value.utility.verify_webhook_signature.return_value = None
    with patch.dict(sys.modules, {'razorpay': mod}):
        yield mod


@pytest.fixture
def mock_sub():
    """Create a mock TenantSubscription."""
    sub = MagicMock()
    sub.id = uuid.uuid4()
    sub.organization_id = uuid.uuid4()
    sub.organization = MagicMock(id=sub.organization_id)
    sub.status = 'trial'
    sub.plan_id = uuid.uuid4()
    sub.razorpay_sub_id = 'sub_test123'
    sub.current_period_count = 42
    sub.save = MagicMock()
    sub.transition_to = MagicMock()
    return sub


def _webhook_body(event_type, sub_id='sub_test123', plan_id='plan_xyz', event_id=None):
    return {
        'id': event_id or f'evt_{uuid.uuid4().hex[:8]}',
        'event': event_type,
        'payload': {
            'subscription': {
                'entity': {
                    'id': sub_id,
                    'plan_id': plan_id,
                }
            }
        }
    }


class TestWebhookView:

    @pytest.mark.django_db
    def test_invalid_signature_returns_400(self, api_rf, mock_razorpay):
        """Invalid Razorpay signature should return 400."""
        from apps.billing.views import WebhookView

        body = _webhook_body('subscription.activated')
        request = api_rf.post(
            '/api/billing/webhook/',
            data=json.dumps(body),
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='bad_sig',
        )

        mock_razorpay.Client.return_value.utility.verify_webhook_signature.side_effect = Exception('bad sig')

        with patch('apps.billing.views.settings') as mock_settings:
            mock_settings.RAZORPAY_WEBHOOK_SECRET = 'webhook_secret'
            mock_settings.RAZORPAY_KEY_ID = 'key_id'
            mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'

            view = WebhookView.as_view()
            response = view(request)

        assert response.status_code == 400

    @pytest.mark.django_db
    def test_subscription_activated_sets_active(self, api_rf, mock_sub, mock_razorpay):
        """subscription.activated event should transition to ACTIVE."""
        from apps.billing.views import WebhookView

        body = _webhook_body('subscription.activated')
        request = api_rf.post(
            '/api/billing/webhook/',
            data=json.dumps(body),
            content_type='application/json',
        )

        with patch('apps.billing.views.settings') as mock_settings, \
             patch('apps.billing.views.TenantSubscription') as MockSub, \
             patch('apps.billing.views.PaymentEvent') as MockPE, \
             patch('apps.billing.views.SubscriptionPlan') as MockPlan:

            mock_settings.RAZORPAY_WEBHOOK_SECRET = 'test_secret'
            mock_settings.RAZORPAY_KEY_ID = 'key_id'
            mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'
            MockPE.objects.filter.return_value.exists.return_value = False
            MockPE.objects.create.return_value = MagicMock(processed=False)
            MockSub.objects.filter.return_value.select_related.return_value.first.return_value = mock_sub
            MockSub.Status = MagicMock()
            MockSub.Status.ACTIVE = 'active'
            MockPlan.objects.filter.return_value.first.return_value = None

            view = WebhookView.as_view()
            response = view(request)

        assert response.status_code == 200
        mock_sub.transition_to.assert_called_once()

    @pytest.mark.django_db
    def test_subscription_charged_resets_counter(self, api_rf, mock_sub, mock_razorpay):
        """subscription.charged should reset period count and update dates."""
        from apps.billing.views import WebhookView

        body = _webhook_body('subscription.charged')
        request = api_rf.post(
            '/api/billing/webhook/',
            data=json.dumps(body),
            content_type='application/json',
        )

        with patch('apps.billing.views.settings') as mock_settings, \
             patch('apps.billing.views.TenantSubscription') as MockSub, \
             patch('apps.billing.views.PaymentEvent') as MockPE:

            mock_settings.RAZORPAY_WEBHOOK_SECRET = 'test_secret'
            mock_settings.RAZORPAY_KEY_ID = 'key_id'
            mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'
            MockPE.objects.filter.return_value.exists.return_value = False
            MockPE.objects.create.return_value = MagicMock(processed=False)
            MockSub.objects.filter.return_value.select_related.return_value.first.return_value = mock_sub

            view = WebhookView.as_view()
            response = view(request)

        assert response.status_code == 200
        assert mock_sub.current_period_count == 0
        mock_sub.save.assert_called()

    @pytest.mark.django_db
    def test_subscription_cancelled(self, api_rf, mock_sub, mock_razorpay):
        """subscription.cancelled should transition to CANCELLED."""
        from apps.billing.views import WebhookView

        body = _webhook_body('subscription.cancelled')
        request = api_rf.post(
            '/api/billing/webhook/',
            data=json.dumps(body),
            content_type='application/json',
        )

        with patch('apps.billing.views.settings') as mock_settings, \
             patch('apps.billing.views.TenantSubscription') as MockSub, \
             patch('apps.billing.views.PaymentEvent') as MockPE:

            mock_settings.RAZORPAY_WEBHOOK_SECRET = 'test_secret'
            mock_settings.RAZORPAY_KEY_ID = 'key_id'
            mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'
            MockPE.objects.filter.return_value.exists.return_value = False
            MockPE.objects.create.return_value = MagicMock(processed=False)
            MockSub.objects.filter.return_value.select_related.return_value.first.return_value = mock_sub
            MockSub.Status = MagicMock()
            MockSub.Status.CANCELLED = 'cancelled'

            view = WebhookView.as_view()
            response = view(request)

        assert response.status_code == 200
        mock_sub.transition_to.assert_called_once()

    @pytest.mark.django_db
    def test_payment_failed_sets_past_due(self, api_rf, mock_sub, mock_razorpay):
        """payment.failed should transition to PAST_DUE."""
        from apps.billing.views import WebhookView

        body = _webhook_body('payment.failed')
        request = api_rf.post(
            '/api/billing/webhook/',
            data=json.dumps(body),
            content_type='application/json',
        )

        with patch('apps.billing.views.settings') as mock_settings, \
             patch('apps.billing.views.TenantSubscription') as MockSub, \
             patch('apps.billing.views.PaymentEvent') as MockPE:

            mock_settings.RAZORPAY_WEBHOOK_SECRET = 'test_secret'
            mock_settings.RAZORPAY_KEY_ID = 'key_id'
            mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'
            MockPE.objects.filter.return_value.exists.return_value = False
            MockPE.objects.create.return_value = MagicMock(processed=False)
            MockSub.objects.filter.return_value.select_related.return_value.first.return_value = mock_sub
            MockSub.Status = MagicMock()
            MockSub.Status.PAST_DUE = 'past_due'

            view = WebhookView.as_view()
            response = view(request)

        assert response.status_code == 200
        mock_sub.transition_to.assert_called_once()

    @pytest.mark.django_db
    def test_duplicate_event_returns_already_processed(self, api_rf, mock_razorpay):
        """Duplicate event_id should return already_processed."""
        from apps.billing.views import WebhookView

        body = _webhook_body('subscription.activated', event_id='evt_dup')
        request = api_rf.post(
            '/api/billing/webhook/',
            data=json.dumps(body),
            content_type='application/json',
        )

        with patch('apps.billing.views.settings') as mock_settings, \
             patch('apps.billing.views.PaymentEvent') as MockPE:

            mock_settings.RAZORPAY_WEBHOOK_SECRET = 'test_secret'
            mock_settings.RAZORPAY_KEY_ID = 'key_id'
            mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'
            MockPE.objects.filter.return_value.exists.return_value = True

            view = WebhookView.as_view()
            response = view(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data['status'] == 'already_processed'

    @pytest.mark.django_db
    def test_unknown_sub_stores_event(self, api_rf, mock_razorpay):
        """Unknown razorpay_sub_id should store event but not update any subscription."""
        from apps.billing.views import WebhookView

        body = _webhook_body('subscription.activated', sub_id='sub_unknown')
        request = api_rf.post(
            '/api/billing/webhook/',
            data=json.dumps(body),
            content_type='application/json',
        )

        with patch('apps.billing.views.settings') as mock_settings, \
             patch('apps.billing.views.TenantSubscription') as MockSub, \
             patch('apps.billing.views.PaymentEvent') as MockPE:

            mock_settings.RAZORPAY_WEBHOOK_SECRET = 'test_secret'
            mock_settings.RAZORPAY_KEY_ID = 'key_id'
            mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'
            MockPE.objects.filter.return_value.exists.return_value = False
            MockPE.objects.create.return_value = MagicMock(processed=False)
            MockSub.objects.filter.return_value.select_related.return_value.first.return_value = None

            view = WebhookView.as_view()
            response = view(request)

        assert response.status_code == 200
        MockPE.objects.create.assert_called_once()

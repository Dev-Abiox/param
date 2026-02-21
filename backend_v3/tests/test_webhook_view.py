"""
Tests for the Razorpay WebhookView (billing/views.py).
"""

import json
import uuid
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory


@pytest.fixture
def rf():
    return APIRequestFactory()


def _webhook_request(rf, payload: dict, signature: str = 'valid-sig'):
    """Build a POST request mimicking a Razorpay webhook call."""
    request = rf.post(
        '/api/billing/webhook/',
        data=json.dumps(payload),
        content_type='application/json',
    )
    request.META['HTTP_X_RAZORPAY_SIGNATURE'] = signature
    return request


def _subscription_payload(event_type: str, razorpay_sub_id: str = 'sub_test123',
                          plan_id: str = '', event_id: str = ''):
    return {
        'id': event_id or f'evt_{uuid.uuid4().hex[:12]}',
        'event': event_type,
        'payload': {
            'subscription': {
                'entity': {
                    'id': razorpay_sub_id,
                    'plan_id': plan_id,
                }
            }
        }
    }


class TestWebhookView:

    @pytest.fixture(autouse=True)
    def disable_throttle(self):
        """Disable webhook rate throttling for tests (requires Redis)."""
        from apps.billing.views import WebhookView
        original = WebhookView.throttle_classes
        WebhookView.throttle_classes = []
        yield
        WebhookView.throttle_classes = original

    @patch('apps.billing.views.settings')
    def test_missing_webhook_secret_returns_503(self, mock_settings, rf):
        """Should return 503 when RAZORPAY_WEBHOOK_SECRET is not configured."""
        from apps.billing.views import WebhookView

        mock_settings.RAZORPAY_WEBHOOK_SECRET = ''
        payload = _subscription_payload('subscription.activated')
        request = _webhook_request(rf, payload)

        view = WebhookView.as_view()
        response = view(request)

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @patch('razorpay.Client')
    @patch('apps.billing.views.settings')
    def test_invalid_signature_returns_400(self, mock_settings, MockClient, rf):
        """Should return 400 when Razorpay signature verification fails."""
        from apps.billing.views import WebhookView

        mock_settings.RAZORPAY_WEBHOOK_SECRET = 'wh_secret'
        mock_settings.RAZORPAY_KEY_ID = 'key_id'
        mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'

        mock_client = MagicMock()
        mock_client.utility.verify_webhook_signature.side_effect = Exception('bad sig')
        MockClient.return_value = mock_client

        payload = _subscription_payload('subscription.activated')
        request = _webhook_request(rf, payload, signature='bad-sig')

        view = WebhookView.as_view()
        response = view(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch('razorpay.Client')
    @patch('apps.billing.views.settings')
    @patch('apps.billing.views.PaymentEvent')
    def test_duplicate_event_returns_already_processed(self, MockPE, mock_settings,
                                                        MockClient, rf):
        """Should return 200 with 'already_processed' for duplicate event IDs."""
        from apps.billing.views import WebhookView

        mock_settings.RAZORPAY_WEBHOOK_SECRET = 'wh_secret'
        mock_settings.RAZORPAY_KEY_ID = 'key_id'
        mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'

        mock_client = MagicMock()
        MockClient.return_value = mock_client

        MockPE.objects.filter.return_value.exists.return_value = True  # already processed

        payload = _subscription_payload('subscription.activated', event_id='evt_dup123')
        request = _webhook_request(rf, payload)

        view = WebhookView.as_view()
        response = view(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'already_processed'

    @patch('razorpay.Client')
    @patch('apps.billing.views.settings')
    @patch('apps.billing.views.PaymentEvent')
    @patch('apps.billing.views.TenantSubscription')
    @patch('apps.billing.views.SubscriptionPlan')
    def test_subscription_activated_updates_status(self, MockPlan, MockSub,
                                                    MockPE, mock_settings,
                                                    MockClient, rf):
        """subscription.activated should transition sub to ACTIVE."""
        from apps.billing.views import WebhookView

        mock_settings.RAZORPAY_WEBHOOK_SECRET = 'wh_secret'
        mock_settings.RAZORPAY_KEY_ID = 'key_id'
        mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'

        mock_client = MagicMock()
        MockClient.return_value = mock_client

        MockPE.objects.filter.return_value.exists.return_value = False
        mock_pe = MagicMock()
        MockPE.objects.create.return_value = mock_pe

        mock_sub = MagicMock()
        mock_sub.organization_id = str(uuid.uuid4())
        mock_sub.organization = MagicMock()
        MockSub.objects.filter.return_value.select_related.return_value.first.return_value = mock_sub
        MockSub.Status.ACTIVE = 'ACTIVE'

        MockPlan.objects.filter.return_value.first.return_value = None  # no plan upgrade

        payload = _subscription_payload('subscription.activated', razorpay_sub_id='sub_123')
        request = _webhook_request(rf, payload)

        view = WebhookView.as_view()
        response = view(request)

        assert response.status_code == status.HTTP_200_OK
        mock_sub.transition_to.assert_called_once_with('ACTIVE')
        mock_sub.save.assert_called_once()
        mock_pe.save.assert_called()

    @patch('razorpay.Client')
    @patch('apps.billing.views.settings')
    @patch('apps.billing.views.PaymentEvent')
    @patch('apps.billing.views.TenantSubscription')
    def test_subscription_charged_resets_counter(self, MockSub, MockPE,
                                                  mock_settings, MockClient, rf):
        """subscription.charged should reset current_period_count to 0."""
        from apps.billing.views import WebhookView

        mock_settings.RAZORPAY_WEBHOOK_SECRET = 'wh_secret'
        mock_settings.RAZORPAY_KEY_ID = 'key_id'
        mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'

        mock_client = MagicMock()
        MockClient.return_value = mock_client

        MockPE.objects.filter.return_value.exists.return_value = False
        mock_pe = MagicMock()
        MockPE.objects.create.return_value = mock_pe

        mock_sub = MagicMock()
        mock_sub.organization_id = str(uuid.uuid4())
        mock_sub.organization = MagicMock()
        mock_sub.current_period_count = 42
        MockSub.objects.filter.return_value.select_related.return_value.first.return_value = mock_sub

        payload = _subscription_payload('subscription.charged')
        request = _webhook_request(rf, payload)

        view = WebhookView.as_view()
        response = view(request)

        assert response.status_code == status.HTTP_200_OK
        assert mock_sub.current_period_count == 0

    @patch('razorpay.Client')
    @patch('apps.billing.views.settings')
    @patch('apps.billing.views.PaymentEvent')
    @patch('apps.billing.views.TenantSubscription')
    def test_subscription_cancelled_sets_status(self, MockSub, MockPE,
                                                 mock_settings, MockClient, rf):
        """subscription.cancelled should transition sub to CANCELLED."""
        from apps.billing.views import WebhookView

        mock_settings.RAZORPAY_WEBHOOK_SECRET = 'wh_secret'
        mock_settings.RAZORPAY_KEY_ID = 'key_id'
        mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'

        mock_client = MagicMock()
        MockClient.return_value = mock_client

        MockPE.objects.filter.return_value.exists.return_value = False
        mock_pe = MagicMock()
        MockPE.objects.create.return_value = mock_pe

        mock_sub = MagicMock()
        mock_sub.organization_id = str(uuid.uuid4())
        mock_sub.organization = MagicMock()
        MockSub.objects.filter.return_value.select_related.return_value.first.return_value = mock_sub
        MockSub.Status.CANCELLED = 'CANCELLED'

        payload = _subscription_payload('subscription.cancelled')
        request = _webhook_request(rf, payload)

        view = WebhookView.as_view()
        response = view(request)

        assert response.status_code == status.HTTP_200_OK
        mock_sub.transition_to.assert_called_once_with('CANCELLED')

    @patch('razorpay.Client')
    @patch('apps.billing.views.settings')
    @patch('apps.billing.views.PaymentEvent')
    @patch('apps.billing.views.TenantSubscription')
    def test_payment_failed_sets_past_due(self, MockSub, MockPE,
                                           mock_settings, MockClient, rf):
        """payment.failed should transition sub to PAST_DUE."""
        from apps.billing.views import WebhookView

        mock_settings.RAZORPAY_WEBHOOK_SECRET = 'wh_secret'
        mock_settings.RAZORPAY_KEY_ID = 'key_id'
        mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'

        mock_client = MagicMock()
        MockClient.return_value = mock_client

        MockPE.objects.filter.return_value.exists.return_value = False
        mock_pe = MagicMock()
        MockPE.objects.create.return_value = mock_pe

        mock_sub = MagicMock()
        mock_sub.organization_id = str(uuid.uuid4())
        mock_sub.organization = MagicMock()
        MockSub.objects.filter.return_value.select_related.return_value.first.return_value = mock_sub
        MockSub.Status.PAST_DUE = 'PAST_DUE'

        payload = _subscription_payload('payment.failed')
        request = _webhook_request(rf, payload)

        view = WebhookView.as_view()
        response = view(request)

        assert response.status_code == status.HTTP_200_OK
        mock_sub.transition_to.assert_called_once_with('PAST_DUE')

    @patch('razorpay.Client')
    @patch('apps.billing.views.settings')
    @patch('apps.billing.views.PaymentEvent')
    @patch('apps.billing.views.TenantSubscription')
    def test_no_matching_sub_still_stores_event(self, MockSub, MockPE,
                                                 mock_settings, MockClient, rf):
        """Webhook for unknown sub should store the event but not crash."""
        from apps.billing.views import WebhookView

        mock_settings.RAZORPAY_WEBHOOK_SECRET = 'wh_secret'
        mock_settings.RAZORPAY_KEY_ID = 'key_id'
        mock_settings.RAZORPAY_KEY_SECRET = 'key_secret'

        mock_client = MagicMock()
        MockClient.return_value = mock_client

        MockPE.objects.filter.return_value.exists.return_value = False
        mock_pe = MagicMock()
        MockPE.objects.create.return_value = mock_pe

        # No matching subscription
        MockSub.objects.filter.return_value.select_related.return_value.first.return_value = None

        payload = _subscription_payload('subscription.activated', razorpay_sub_id='sub_unknown')
        request = _webhook_request(rf, payload)

        view = WebhookView.as_view()
        response = view(request)

        assert response.status_code == status.HTTP_200_OK
        MockPE.objects.create.assert_called_once()

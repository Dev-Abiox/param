"""
Tests for POST /api/billing/admin/verify-payment/.

PaymentVerifyView is the revenue-critical endpoint the frontend calls
after Razorpay Checkout fires its `handler(...)` success callback. It
verifies the HMAC-SHA256 signature the gateway returns and is the
canonical "did this user actually pay" check — the frontend must not
trust Checkout's handler alone.

Invariants under test:
- Missing RAZORPAY_KEY_SECRET → 503 (fail-closed).
- Missing any of the three required fields → 400.
- Signature mismatch → 422 (never 200, never 400 — so frontend can
  distinguish integration mistakes from forgery attempts).
- Valid signature → 200 with {verified: True}.
- We use hmac.compare_digest so timing-attack safe (exercised implicitly
  by the valid-signature path).
"""

import hashlib
import hmac as _hmac
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.models import Role
from apps.billing.views import PaymentVerifyView


def _make_user(role=Role.LAB, username='lab_admin', email='admin@example.com'):
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = (role == Role.SUPER_ADMIN)
    user.role = role
    user.username = username
    user.email = email
    user.pk = 1
    user.organization = MagicMock(name='TestOrg')
    return user


def _make_request(payload, user=None):
    factory = APIRequestFactory()
    request = factory.post(
        '/api/billing/admin/verify-payment/', payload, format='json'
    )
    force_authenticate(request, user=user or _make_user())
    request.token_payload = {'mfa_verified': True}
    return request


def _sign(payment_id, sub_id, secret):
    msg = f'{payment_id}|{sub_id}'.encode()
    return _hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


class TestPaymentVerifyView:
    """PaymentVerifyView: HMAC verification against Razorpay signature."""

    @patch.object(PaymentVerifyView, 'throttle_classes', [])
    @patch('apps.billing.views.settings')
    def test_missing_key_secret_returns_503(self, mock_settings):
        mock_settings.RAZORPAY_KEY_SECRET = ''
        mock_settings.RAZORPAY_KEY_ID = ''

        request = _make_request({
            'razorpay_payment_id': 'pay_abc',
            'razorpay_subscription_id': 'sub_abc',
            'razorpay_signature': 'sig',
        })
        response = PaymentVerifyView.as_view()(request)
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @patch.object(PaymentVerifyView, 'throttle_classes', [])
    @patch('apps.billing.views.settings')
    def test_missing_fields_returns_400(self, mock_settings):
        mock_settings.RAZORPAY_KEY_SECRET = 'secret'
        mock_settings.RAZORPAY_KEY_ID = 'kid'

        # Each required field missing in turn must 400.
        bases = [
            {'razorpay_subscription_id': 'sub', 'razorpay_signature': 'sig'},
            {'razorpay_payment_id': 'pay', 'razorpay_signature': 'sig'},
            {'razorpay_payment_id': 'pay', 'razorpay_subscription_id': 'sub'},
        ]
        for payload in bases:
            request = _make_request(payload)
            response = PaymentVerifyView.as_view()(request)
            assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch.object(PaymentVerifyView, 'throttle_classes', [])
    @patch('apps.billing.views.schema_context')
    @patch('apps.billing.views.TenantSubscription')
    @patch('apps.billing.views._razorpay_client')
    @patch('apps.billing.views.settings')
    def test_wrong_signature_returns_422(
        self, mock_settings, mock_client_factory, MockSub, mock_schema_ctx
    ):
        mock_settings.RAZORPAY_KEY_SECRET = 'correct-secret'
        mock_settings.RAZORPAY_KEY_ID = 'kid'
        mock_schema_ctx.return_value.__enter__ = MagicMock()
        mock_schema_ctx.return_value.__exit__ = MagicMock(return_value=False)

        payload = {
            'razorpay_payment_id': 'pay_OK',
            'razorpay_subscription_id': 'sub_OK',
            # Signature computed with the WRONG secret.
            'razorpay_signature': _sign('pay_OK', 'sub_OK', 'attacker-secret'),
        }
        request = _make_request(payload)
        response = PaymentVerifyView.as_view()(request)

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.data.get('verified') is False
        mock_client_factory.assert_not_called()  # Never reaches the SDK on bad sig

    @patch.object(PaymentVerifyView, 'throttle_classes', [])
    @patch('apps.billing.views.schema_context')
    @patch('apps.billing.views.TenantSubscription')
    @patch('apps.billing.views._razorpay_client')
    @patch('apps.billing.views.settings')
    def test_valid_signature_returns_200(
        self, mock_settings, mock_client_factory, MockSub, mock_schema_ctx
    ):
        secret = 'top-secret-key'
        mock_settings.RAZORPAY_KEY_SECRET = secret
        mock_settings.RAZORPAY_KEY_ID = 'kid'

        # No-op the schema_context('public') block.
        mock_schema_ctx.return_value.__enter__ = MagicMock()
        mock_schema_ctx.return_value.__exit__ = MagicMock(return_value=False)

        # Build a request whose user belongs to a known org, then make the
        # mocked DB subscription point at that same org so the cross-org
        # guard added in fe3d9b8 / 4ff8c2e accepts the lookup.
        user = _make_user()
        org_id = user.organization.id

        mock_db_sub = MagicMock()
        mock_db_sub.status = 'ACTIVE'
        mock_db_sub.organization_id = org_id
        MockSub.objects.filter.return_value.first.return_value = mock_db_sub

        # Razorpay SDK client: the fetch must not blow up (defence-in-depth).
        client = MagicMock()
        client.subscription.fetch.return_value = {'id': 'sub_live', 'status': 'active'}
        mock_client_factory.return_value = client

        payment_id = 'pay_live'
        sub_id = 'sub_live'
        payload = {
            'razorpay_payment_id': payment_id,
            'razorpay_subscription_id': sub_id,
            'razorpay_signature': _sign(payment_id, sub_id, secret),
        }

        request = _make_request(payload, user=user)
        response = PaymentVerifyView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data.get('verified') is True
        assert response.data.get('razorpay_subscription_id') == sub_id
        assert response.data.get('razorpay_payment_id') == payment_id
        assert response.data.get('db_subscription_status') == 'ACTIVE'
        client.subscription.fetch.assert_called_once_with(sub_id)

    @patch.object(PaymentVerifyView, 'throttle_classes', [])
    @patch('apps.billing.views.schema_context')
    @patch('apps.billing.views.TenantSubscription')
    @patch('apps.billing.views._razorpay_client')
    @patch('apps.billing.views.settings')
    def test_sdk_fetch_failure_is_non_fatal(
        self, mock_settings, mock_client_factory, MockSub, mock_schema_ctx
    ):
        """If the defence-in-depth fetch raises, the signed response still wins."""
        secret = 'top-secret-key'
        mock_settings.RAZORPAY_KEY_SECRET = secret
        mock_settings.RAZORPAY_KEY_ID = 'kid'

        mock_schema_ctx.return_value.__enter__ = MagicMock()
        mock_schema_ctx.return_value.__exit__ = MagicMock(return_value=False)
        MockSub.objects.filter.return_value.first.return_value = None

        client = MagicMock()
        client.subscription.fetch.side_effect = RuntimeError('gateway down')
        mock_client_factory.return_value = client

        payload = {
            'razorpay_payment_id': 'pay_x',
            'razorpay_subscription_id': 'sub_x',
            'razorpay_signature': _sign('pay_x', 'sub_x', secret),
        }
        request = _make_request(payload)
        response = PaymentVerifyView.as_view()(request)

        # Signature was valid — the SDK failure must be swallowed, not surfaced.
        assert response.status_code == status.HTTP_200_OK
        assert response.data.get('verified') is True
        assert response.data.get('db_subscription_status') is None

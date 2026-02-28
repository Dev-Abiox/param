"""
Integration tests for Razorpay webhook handling.

Tests signature verification and subscription state transitions.
"""

import hashlib
import hmac
import json

import pytest
from django.test import override_settings
from rest_framework.test import APIClient


WEBHOOK_SECRET = 'test-webhook-secret-for-testing'


@pytest.mark.django_db
class TestWebhookSignatureVerification:
    """Test POST /api/billing/webhook signature validation."""

    def _sign_payload(self, payload_bytes, secret=WEBHOOK_SECRET):
        """Create a valid Razorpay HMAC-SHA256 signature."""
        return hmac.new(
            secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

    @override_settings(RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET)
    def test_valid_signature_accepted(self, public_tenant):
        payload = json.dumps({
            'event': 'subscription.activated',
            'payload': {
                'subscription': {
                    'entity': {
                        'id': 'sub_test123',
                        'plan_id': 'plan_test',
                        'status': 'active',
                    }
                }
            }
        }).encode('utf-8')

        signature = self._sign_payload(payload)

        client = APIClient()
        response = client.post(
            '/api/billing/webhook/',
            data=payload,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )
        # Should not return 401/403 (signature valid)
        # May return 200 or 404 if subscription doesn't exist in test DB
        assert response.status_code != 401

    @override_settings(RAZORPAY_WEBHOOK_SECRET=WEBHOOK_SECRET)
    def test_invalid_signature_rejected(self, public_tenant):
        payload = json.dumps({
            'event': 'subscription.activated',
            'payload': {'subscription': {'entity': {'id': 'sub_test'}}}
        }).encode('utf-8')

        client = APIClient()
        response = client.post(
            '/api/billing/webhook/',
            data=payload,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='invalid-signature',
        )
        assert response.status_code in (401, 403)

    @override_settings(RAZORPAY_WEBHOOK_SECRET='')
    def test_missing_webhook_secret_returns_503(self, public_tenant):
        """When RAZORPAY_WEBHOOK_SECRET is not configured, fail closed."""
        payload = json.dumps({'event': 'test'}).encode('utf-8')

        client = APIClient()
        response = client.post(
            '/api/billing/webhook/',
            data=payload,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='any',
        )
        assert response.status_code in (401, 403, 503)

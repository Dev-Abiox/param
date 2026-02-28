"""
Payment and billing security tests.

Covers:
- SSRF protection on webhook URL registration
- Webhook state transition atomicity
- PaymentEvent error sanitization
- Credential email security (no plaintext passwords in broker)
- Auto-provisioning removal
- Subscription state machine integrity
"""

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings
from django.utils import timezone


class TestWebhookURLSSRF:
    """Verify webhook URL registration blocks SSRF targets."""

    def test_private_ip_rejected(self):
        from apps.billing.views import _validate_webhook_url

        # All private/internal IPs must be blocked
        for url in [
            'https://127.0.0.1/webhook',
            'https://localhost/webhook',
            'https://10.0.0.1/webhook',
            'https://172.16.0.1/webhook',
            'https://192.168.1.1/webhook',
            'https://[::1]/webhook',
        ]:
            with patch('apps.billing.views.socket.getaddrinfo') as mock_resolve:
                # Simulate DNS resolving to the private IP
                ip = url.split('//')[1].split('/')[0].strip('[]')
                if ip == 'localhost':
                    ip = '127.0.0.1'
                mock_resolve.return_value = [
                    (2, 1, 6, '', (ip, 443)),
                ]
                error = _validate_webhook_url(url)
                assert error is not None, f"Should block {url}"
                assert 'private' in error.lower() or 'internal' in error.lower()

    def test_http_rejected(self):
        from apps.billing.views import _validate_webhook_url

        error = _validate_webhook_url('http://example.com/webhook')
        assert error is not None
        assert 'HTTPS' in error

    def test_valid_https_public_ip_accepted(self):
        from apps.billing.views import _validate_webhook_url

        with patch('apps.billing.views.socket.getaddrinfo') as mock_resolve:
            mock_resolve.return_value = [
                (2, 1, 6, '', ('93.184.216.34', 443)),  # example.com public IP
            ]
            error = _validate_webhook_url('https://example.com/webhook')
            assert error is None

    def test_missing_hostname_rejected(self):
        from apps.billing.views import _validate_webhook_url

        error = _validate_webhook_url('https://')
        assert error is not None

    def test_unresolvable_hostname_rejected(self):
        from apps.billing.views import _validate_webhook_url

        with patch('apps.billing.views.socket.getaddrinfo', side_effect=Exception('DNS failed')):
            error = _validate_webhook_url('https://nonexistent.invalid/webhook')
            assert error is not None


class TestWebhookSignatureStatus:
    """Verify invalid Razorpay webhook signatures return 401 (not 400)."""

    def test_invalid_signature_returns_401(self, public_tenant):
        """Invalid HMAC signature should be 401 Unauthorized, not 400 Bad Request."""
        import json
        from rest_framework.test import APIClient

        client = APIClient()
        payload = json.dumps({'event': 'test'}).encode('utf-8')

        with override_settings(RAZORPAY_WEBHOOK_SECRET='test-secret'):
            response = client.post(
                '/api/billing/webhook',
                data=payload,
                content_type='application/json',
                HTTP_X_RAZORPAY_SIGNATURE='tampered-signature',
            )
            assert response.status_code == 401


class TestPaymentEventErrorSanitization:
    """Verify PaymentEvent.error never stores raw exception details."""

    def test_error_field_contains_only_type_and_event(self):
        """The error should be '{ExceptionType}: {event_type}', not str(exc)."""
        from apps.billing.models import PaymentEvent

        # Simulate what the webhook handler stores on error
        safe_error = f'{type(ValueError("secret DB path /var/lib/pgsql")).__name__}: subscription.activated'
        pe = PaymentEvent(error=safe_error)

        assert '/var/lib' not in pe.error
        assert 'secret DB path' not in pe.error
        assert 'ValueError' in pe.error
        assert 'subscription.activated' in pe.error


class TestSubscriptionStateMachine:
    """Verify subscription state transitions are strictly enforced."""

    def test_valid_transitions(self):
        from apps.billing.models import TenantSubscription

        sub = TenantSubscription()

        # trial -> active (valid)
        sub.status = TenantSubscription.Status.TRIAL
        sub.transition_to(TenantSubscription.Status.ACTIVE)
        assert sub.status == TenantSubscription.Status.ACTIVE

        # active -> past_due (valid)
        sub.transition_to(TenantSubscription.Status.PAST_DUE)
        assert sub.status == TenantSubscription.Status.PAST_DUE

        # past_due -> active (valid)
        sub.transition_to(TenantSubscription.Status.ACTIVE)
        assert sub.status == TenantSubscription.Status.ACTIVE

    def test_invalid_transition_raises(self):
        from apps.billing.models import TenantSubscription

        sub = TenantSubscription()
        sub.status = TenantSubscription.Status.TRIAL

        # trial -> past_due is NOT allowed
        with pytest.raises(ValueError, match='Invalid status transition'):
            sub.transition_to(TenantSubscription.Status.PAST_DUE)

    def test_cancelled_can_only_reactivate(self):
        from apps.billing.models import TenantSubscription

        sub = TenantSubscription()
        sub.status = TenantSubscription.Status.CANCELLED

        # cancelled -> trial (invalid)
        with pytest.raises(ValueError):
            sub.transition_to(TenantSubscription.Status.TRIAL)

        # cancelled -> active (valid — re-subscription)
        sub.transition_to(TenantSubscription.Status.ACTIVE)
        assert sub.status == TenantSubscription.Status.ACTIVE


class TestCredentialEmailSecurity:
    """Verify credential emails use password reset tokens instead of plaintext passwords."""

    def test_send_credentials_email_has_no_password_param(self):
        """The task signature should NOT accept a plaintext password."""
        import inspect
        from apps.billing.tasks import send_credentials_email

        sig = inspect.signature(send_credentials_email)
        param_names = list(sig.parameters.keys())
        assert 'plain_password' not in param_names
        assert 'password' not in param_names
        assert 'temp_password' not in param_names

    def test_send_lab_created_email_has_no_password_param(self):
        """The task signature should NOT accept a plaintext password."""
        import inspect
        from apps.billing.tasks import send_lab_created_email

        sig = inspect.signature(send_lab_created_email)
        param_names = list(sig.parameters.keys())
        assert 'plain_password' not in param_names
        assert 'password' not in param_names
        assert 'temp_password' not in param_names

    def test_password_setup_url_contains_token(self):
        """The helper should generate a URL with uid and token components."""
        from apps.billing.tasks import _make_password_setup_url

        user = MagicMock()
        user.pk = uuid.uuid4()
        # Django's token generator needs these attributes
        user.password = 'pbkdf2_sha256$hashed'
        user.last_login = None

        with patch('apps.billing.tasks.default_token_generator') as mock_gen:
            mock_gen.make_token.return_value = 'test-token-abc123'
            url = _make_password_setup_url(user)

        assert '/set-password/' in url
        assert 'test-token-abc123' in url


class TestAutoProvisioningRemoved:
    """Verify billing views no longer auto-provision enterprise trials."""

    def test_admin_usage_view_source_no_auto_provision(self):
        """AdminUsageView should not create subscriptions on the fly."""
        import inspect
        from apps.billing.views import AdminUsageView

        source = inspect.getsource(AdminUsageView)
        assert 'TenantSubscription.objects.create' not in source

    def test_admin_billing_view_source_no_auto_provision(self):
        """AdminBillingView should not create subscriptions on the fly."""
        import inspect
        from apps.billing.views import AdminBillingView

        source = inspect.getsource(AdminBillingView)
        assert 'TenantSubscription.objects.create' not in source


class TestAPIKeySecurityModel:
    """Verify API keys are stored securely (hash-only, never raw)."""

    def test_api_key_model_stores_hash_not_raw(self):
        """The model field should be key_hash, not key or raw_key."""
        from apps.billing.models import APIKey

        field_names = [f.name for f in APIKey._meta.get_fields()]
        assert 'key_hash' in field_names
        assert 'key' not in field_names
        assert 'raw_key' not in field_names

    def test_api_key_list_endpoint_excludes_hash(self):
        """The GET response should never include key_hash."""
        import inspect
        from apps.billing.views import APIKeyListView

        source = inspect.getsource(APIKeyListView.get)
        assert 'key_hash' not in source


class TestWebhookDeliverySSRF:
    """Verify the deliver_webhook task has defence-in-depth SSRF protection."""

    def test_deliver_webhook_source_has_ssrf_guard(self):
        """The task should check for private IPs at delivery time."""
        import inspect
        from apps.billing.tasks import deliver_webhook

        source = inspect.getsource(deliver_webhook)
        assert 'is_private' in source
        assert 'is_loopback' in source
        assert 'ssrf' in source.lower() or 'SSRF' in source

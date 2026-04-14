"""
Integration tests for the password-reset flow.

Covers:
- ForgotPasswordView — always returns 200 to avoid account enumeration,
  stores a token in Redis cache, triggers an email.
- ResetPasswordView — consumes the token atomically, validates the new
  password, saves it, and revokes outstanding refresh tokens.

Security invariants we deliberately assert:
- Unknown identifier still returns 200 with the same body as a hit
  (enumeration protection).
- Token can only be used once: second attempt returns 400.
- Invalid / missing token returns 400.
- Weak passwords are rejected.
- Password change invalidates all active refresh tokens for the user.
"""

from unittest.mock import patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.core.views import ForgotPasswordView, ResetPasswordView


@pytest.mark.django_db
class TestForgotPasswordView:
    """POST /api/auth/forgot-password"""

    @patch.object(ForgotPasswordView, 'throttle_classes', [])
    @patch('django.core.mail.send_mail')
    def test_existing_user_returns_200_and_caches_token(
        self, mock_send_mail, authenticated_lab_user
    ):
        user, _ = authenticated_lab_user
        client = APIClient()

        response = client.post(
            '/api/auth/forgot-password',
            {'identifier': user.username},
            format='json',
        )

        assert response.status_code == 200
        assert 'detail' in response.json()
        # A cache key prefixed with pwd_reset_ should now exist holding
        # the user id. We can't predict the token, but we can verify
        # send_mail was called with a URL containing a token.
        assert mock_send_mail.called
        call_kwargs = mock_send_mail.call_args.kwargs or mock_send_mail.call_args[1]
        message = call_kwargs.get('message', '') if call_kwargs else ''
        assert 'reset-password?token=' in message

    @patch.object(ForgotPasswordView, 'throttle_classes', [])
    @patch('django.core.mail.send_mail')
    def test_unknown_identifier_still_returns_200(
        self, mock_send_mail, public_tenant
    ):
        # Account-enumeration protection: an unknown user must get the
        # same response shape a known one would.
        client = APIClient()
        response = client.post(
            '/api/auth/forgot-password',
            {'identifier': 'nobody-here@example.test'},
            format='json',
        )
        assert response.status_code == 200
        assert 'detail' in response.json()
        mock_send_mail.assert_not_called()

    @patch.object(ForgotPasswordView, 'throttle_classes', [])
    @patch('django.core.mail.send_mail')
    def test_empty_identifier_returns_200_without_sending(
        self, mock_send_mail, public_tenant
    ):
        client = APIClient()
        response = client.post(
            '/api/auth/forgot-password',
            {'identifier': '   '},
            format='json',
        )
        assert response.status_code == 200
        mock_send_mail.assert_not_called()

    @patch.object(ForgotPasswordView, 'throttle_classes', [])
    @patch('django.core.mail.send_mail')
    def test_lookup_by_email_is_case_insensitive(
        self, mock_send_mail, authenticated_lab_user
    ):
        user, _ = authenticated_lab_user
        client = APIClient()
        response = client.post(
            '/api/auth/forgot-password',
            {'identifier': user.email.upper()},
            format='json',
        )
        assert response.status_code == 200
        assert mock_send_mail.called


@pytest.mark.django_db
class TestResetPasswordView:
    """POST /api/auth/reset-password"""

    def _issue_token_for(self, user):
        """Helper: shortcut the cache write the way ForgotPasswordView does."""
        import secrets
        token = secrets.token_urlsafe(48)
        cache.set(f'pwd_reset_{token}', str(user.id), timeout=900)
        return token

    @patch.object(ResetPasswordView, 'throttle_classes', [])
    def test_valid_token_resets_password_and_consumes_token(
        self, authenticated_lab_user
    ):
        user, _ = authenticated_lab_user
        token = self._issue_token_for(user)
        new_password = 'FreshStrongPass2026!'

        client = APIClient()
        response = client.post(
            '/api/auth/reset-password',
            {'token': token, 'new_password': new_password},
            format='json',
        )

        assert response.status_code == 200
        # Token must be gone from cache after a successful reset.
        assert cache.get(f'pwd_reset_{token}') is None
        # The new password should authenticate.
        user.refresh_from_db()
        assert user.check_password(new_password)

    @patch.object(ResetPasswordView, 'throttle_classes', [])
    def test_reusing_token_returns_400(self, authenticated_lab_user):
        user, _ = authenticated_lab_user
        token = self._issue_token_for(user)

        client = APIClient()
        first = client.post(
            '/api/auth/reset-password',
            {'token': token, 'new_password': 'FreshStrongPass2026!'},
            format='json',
        )
        assert first.status_code == 200

        second = client.post(
            '/api/auth/reset-password',
            {'token': token, 'new_password': 'AnotherStrongPass2026!'},
            format='json',
        )
        assert second.status_code == 400
        assert 'Invalid' in second.json()['error'] or 'expired' in second.json()['error']

    @patch.object(ResetPasswordView, 'throttle_classes', [])
    def test_invalid_token_returns_400(self, public_tenant):
        client = APIClient()
        response = client.post(
            '/api/auth/reset-password',
            {'token': 'not-a-real-token', 'new_password': 'FreshStrongPass2026!'},
            format='json',
        )
        assert response.status_code == 400

    @patch.object(ResetPasswordView, 'throttle_classes', [])
    def test_missing_token_or_password_returns_400(self, public_tenant):
        client = APIClient()
        r1 = client.post('/api/auth/reset-password', {'new_password': 'x' * 20}, format='json')
        r2 = client.post('/api/auth/reset-password', {'token': 'anything'}, format='json')
        assert r1.status_code == 400
        assert r2.status_code == 400

    @patch.object(ResetPasswordView, 'throttle_classes', [])
    def test_weak_password_is_rejected(self, authenticated_lab_user):
        user, _ = authenticated_lab_user
        token = self._issue_token_for(user)

        client = APIClient()
        response = client.post(
            '/api/auth/reset-password',
            {'token': token, 'new_password': '123'},
            format='json',
        )
        # Django's validators will reject short / common passwords.
        assert response.status_code == 400
        assert 'error' in response.json()

    @patch.object(ResetPasswordView, 'throttle_classes', [])
    def test_reset_revokes_active_refresh_tokens(self, authenticated_lab_user):
        from datetime import timedelta
        from django.utils import timezone
        from django_tenants.utils import tenant_context
        from apps.core.models import RefreshToken as RT

        user, _ = authenticated_lab_user
        # Seed a refresh token in the same tenant the user lives in.
        with tenant_context(user.organization):
            rt = RT.objects.create(
                user=user,
                token_hash='deadbeef' * 8,
                is_revoked=False,
                expires_at=timezone.now() + timedelta(days=30),
            )

        token = self._issue_token_for(user)
        client = APIClient()
        response = client.post(
            '/api/auth/reset-password',
            {'token': token, 'new_password': 'FreshStrongPass2026!'},
            format='json',
        )
        assert response.status_code == 200

        with tenant_context(user.organization):
            rt.refresh_from_db()
            assert rt.is_revoked is True

"""
Tests for the trusted-device MFA-skip flow.

The trusted-device helpers live in apps/core/views.py and let a user skip
the email OTP step for DEVICE_TRUST_TTL_DAYS (currently 30) if they tick
"remember this device" after passing MFA. Critical invariants:

- A cookie issued from IP X must NOT skip MFA when presented from IP Y
  (Phase 7 regression protection — stolen cookies replayed from a
  different network should drop back to OTP).
- Expired tokens must not pass the check.
- A mismatched user must not pass the check even if the token hash is
  technically valid for somebody.
- Creating a device writes an IP-bound row with the correct SHA-256 hash.

We bypass the full LoginView flow because it's already exercised by
test_auth_integration.py and MFAManager is out of scope for this file;
instead we call _create_trusted_device / _check_trusted_device directly
with a fabricated request.
"""

import hashlib
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.core.views import (
    _DEVICE_COOKIE,
    _check_trusted_device,
    _create_trusted_device,
)


def _fake_request(ip='203.0.113.10', user_agent='pytest-agent/1.0', cookie=None):
    """Build a minimal Django request that the helpers will accept."""
    factory = APIRequestFactory()
    req = factory.post('/api/auth/login')
    req.META['REMOTE_ADDR'] = ip
    req.META['HTTP_USER_AGENT'] = user_agent
    if cookie is not None:
        req.COOKIES[_DEVICE_COOKIE] = cookie
    return req


@pytest.mark.django_db
class TestTrustedDeviceCreate:
    """_create_trusted_device writes a DB row and returns the raw token."""

    def test_create_hashes_token_and_stores_ip(self, authenticated_lab_user):
        from django_tenants.utils import tenant_context
        from apps.core.models import TrustedDevice

        user, _ = authenticated_lab_user
        issuing_ip = '198.51.100.42'
        req = _fake_request(ip=issuing_ip)

        with tenant_context(user.organization):
            raw_token = _create_trusted_device(user, req)

        assert raw_token and isinstance(raw_token, str)

        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        with tenant_context(user.organization):
            device = TrustedDevice.objects.get(user=user)
            assert device.token_hash == expected_hash
            assert device.ip_address == issuing_ip
            assert device.user_agent == 'pytest-agent/1.0'
            # TTL is 30 days — allow a 5-minute clock skew window.
            assert device.expires_at > timezone.now() + timedelta(days=29, hours=23)
            assert device.expires_at < timezone.now() + timedelta(days=30, minutes=5)


@pytest.mark.django_db
class TestTrustedDeviceCheck:
    """_check_trusted_device returns True only when all conditions match."""

    def _seed(self, user, ip='198.51.100.42'):
        """Return the raw token for a fresh IP-bound trusted device."""
        from django_tenants.utils import tenant_context
        req = _fake_request(ip=ip)
        with tenant_context(user.organization):
            return _create_trusted_device(user, req)

    def test_same_user_same_ip_is_trusted(self, authenticated_lab_user):
        from django_tenants.utils import tenant_context
        user, _ = authenticated_lab_user
        raw = self._seed(user, ip='198.51.100.42')
        req = _fake_request(ip='198.51.100.42', cookie=raw)

        with tenant_context(user.organization):
            assert _check_trusted_device(user, req) is True

    def test_different_ip_is_rejected(self, authenticated_lab_user):
        from django_tenants.utils import tenant_context
        user, _ = authenticated_lab_user
        raw = self._seed(user, ip='198.51.100.42')
        # Cookie is valid, but it's being presented from a different network.
        req = _fake_request(ip='203.0.113.99', cookie=raw)

        with tenant_context(user.organization):
            assert _check_trusted_device(user, req) is False

    def test_missing_cookie_is_rejected(self, authenticated_lab_user):
        from django_tenants.utils import tenant_context
        user, _ = authenticated_lab_user
        self._seed(user, ip='198.51.100.42')
        req = _fake_request(ip='198.51.100.42')  # no cookie

        with tenant_context(user.organization):
            assert _check_trusted_device(user, req) is False

    def test_unknown_token_is_rejected(self, authenticated_lab_user):
        from django_tenants.utils import tenant_context
        user, _ = authenticated_lab_user
        self._seed(user, ip='198.51.100.42')
        req = _fake_request(ip='198.51.100.42', cookie='not-a-real-token')

        with tenant_context(user.organization):
            assert _check_trusted_device(user, req) is False

    def test_expired_token_is_rejected(self, authenticated_lab_user):
        """Fast-forward the DB row past its expires_at and verify the check fails."""
        from django_tenants.utils import tenant_context
        from apps.core.models import TrustedDevice

        user, _ = authenticated_lab_user
        raw = self._seed(user, ip='198.51.100.42')

        with tenant_context(user.organization):
            TrustedDevice.objects.filter(user=user).update(
                expires_at=timezone.now() - timedelta(minutes=1),
            )

        req = _fake_request(ip='198.51.100.42', cookie=raw)
        with tenant_context(user.organization):
            assert _check_trusted_device(user, req) is False

    def test_token_belonging_to_other_user_is_rejected(
        self, authenticated_lab_user, authenticated_doctor_user
    ):
        """Token hash-match is scoped to (user, hash) pairs."""
        from django_tenants.utils import tenant_context
        lab_user, _ = authenticated_lab_user
        doctor_user, _ = authenticated_doctor_user

        raw = self._seed(lab_user, ip='198.51.100.42')
        req = _fake_request(ip='198.51.100.42', cookie=raw)

        # Present lab_user's cookie as doctor_user — must fail.
        with tenant_context(lab_user.organization):
            assert _check_trusted_device(doctor_user, req) is False

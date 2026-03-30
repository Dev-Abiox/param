"""
Tests for Email OTP MFA method: generation, verification, cooldown,
and integration with login/setup flows.
"""

import hashlib
import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from apps.core.mfa import MFAManager, _mask_email, _OTP_CACHE_KEY, _OTP_COOLDOWN_KEY
from apps.core.models import MFAMethod


def _make_user(user_id=None, email="user@example.com", role="LAB"):
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.email = email
    user.username = "testuser"
    user.role = role
    return user


def _make_mfa_settings(user, method=MFAMethod.EMAIL, enabled=True):
    mfa = MagicMock()
    mfa.mfa_method = method
    mfa.is_enabled = enabled
    mfa.secret_key = ""
    mfa.recovery_email = user.email
    mfa.backup_codes = []
    mfa.verified_at = None
    user.mfa_settings = mfa
    return mfa


class TestMaskEmail:
    def test_normal_email(self):
        assert _mask_email("john@gmail.com") == "j***@gmail.com"

    def test_single_char_local(self):
        assert _mask_email("a@test.com") == "*@test.com"

    def test_empty_email(self):
        assert _mask_email("") == "***"

    def test_none_email(self):
        assert _mask_email(None) == "***"

    def test_no_at_sign(self):
        assert _mask_email("invalid") == "***"


class TestGenerateEmailOTP:
    def setup_method(self):
        cache.clear()

    def test_generates_6_digit_code(self):
        user = _make_user()
        code = MFAManager.generate_email_otp(user)
        assert len(code) == 6
        assert code.isdigit()

    def test_stores_hash_in_cache(self):
        user = _make_user()
        code = MFAManager.generate_email_otp(user)
        cache_key = _OTP_CACHE_KEY.format(user_id=user.id)
        stored = cache.get(cache_key)
        assert stored is not None
        assert stored == hashlib.sha256(code.encode()).hexdigest()

    def test_sets_cooldown(self):
        user = _make_user()
        MFAManager.generate_email_otp(user)
        assert not MFAManager.can_resend_otp(user)


class TestVerifyEmailOTP:
    def setup_method(self):
        cache.clear()

    def test_correct_code_returns_true(self):
        user = _make_user()
        code = MFAManager.generate_email_otp(user)
        assert MFAManager.verify_email_otp(user, code) is True

    def test_wrong_code_returns_false(self):
        user = _make_user()
        MFAManager.generate_email_otp(user)
        assert MFAManager.verify_email_otp(user, "000000") is False

    def test_code_deleted_after_success(self):
        user = _make_user()
        code = MFAManager.generate_email_otp(user)
        MFAManager.verify_email_otp(user, code)
        # Second use should fail
        assert MFAManager.verify_email_otp(user, code) is False

    def test_expired_code_returns_false(self):
        user = _make_user()
        MFAManager.generate_email_otp(user)
        # Clear cache to simulate expiry
        cache.clear()
        assert MFAManager.verify_email_otp(user, "123456") is False


class TestCanResendOTP:
    def setup_method(self):
        cache.clear()

    def test_can_resend_when_no_cooldown(self):
        user = _make_user()
        assert MFAManager.can_resend_otp(user) is True

    def test_cannot_resend_during_cooldown(self):
        user = _make_user()
        MFAManager.generate_email_otp(user)
        assert MFAManager.can_resend_otp(user) is False

    def test_can_resend_after_cooldown_expires(self):
        user = _make_user()
        MFAManager.generate_email_otp(user)
        # Clear cooldown manually
        cooldown_key = _OTP_COOLDOWN_KEY.format(user_id=user.id)
        cache.delete(cooldown_key)
        assert MFAManager.can_resend_otp(user) is True


class TestGetMFAStatus:
    def test_includes_mfa_method(self):
        user = _make_user()
        mfa = _make_mfa_settings(user, method=MFAMethod.EMAIL)
        mfa.verified_at = "2024-01-01"
        status = MFAManager.get_mfa_status(user)
        assert status['mfa_method'] == MFAMethod.EMAIL

    def test_default_method_is_email(self):
        user = _make_user()
        # No mfa_settings
        user.mfa_settings = MagicMock(side_effect=AttributeError)
        delattr(user, 'mfa_settings')
        # Simulate DoesNotExist
        type(user).mfa_settings = property(lambda self: (_ for _ in ()).throw(
            type('DoesNotExist', (Exception,), {})()
        ))
        # Patch MFASettings.DoesNotExist
        with patch('apps.core.mfa.MFASettings') as MockMFA:
            MockMFA.DoesNotExist = Exception
            status = MFAManager.get_mfa_status(user)
        assert status['mfa_method'] == MFAMethod.EMAIL


class TestVerifyCodeEmailMethod:
    def setup_method(self):
        cache.clear()

    def test_email_otp_verify_code(self):
        user = _make_user()
        mfa = _make_mfa_settings(user, method=MFAMethod.EMAIL, enabled=True)
        code = MFAManager.generate_email_otp(user)
        assert MFAManager.verify_code(user, code) is True

    def test_backup_code_works_with_email_method(self):
        user = _make_user()
        backup_code = "ABCD1234"
        mfa = _make_mfa_settings(user, method=MFAMethod.EMAIL, enabled=True)
        mfa.backup_codes = [
            {'hash': hashlib.sha256(backup_code.encode()).hexdigest(), 'used': False}
        ]
        assert MFAManager.verify_code(user, backup_code) is True


class TestSetupMFAEmailMethod:
    def setup_method(self):
        cache.clear()

    @patch('apps.core.mfa.MFASettings')
    @patch('apps.core.mfa.MFAManager._send_otp_email')
    def test_email_setup_returns_masked_email(self, mock_send, MockMFA):
        user = _make_user(email="alice@example.com")
        mock_settings = MagicMock()
        MockMFA.objects.get_or_create.return_value = (mock_settings, True)

        result = MFAManager.setup_mfa(user, email="alice@example.com", method=MFAMethod.EMAIL)

        assert result['method'] == MFAMethod.EMAIL
        assert result['email_masked'] == "a***@example.com"
        mock_send.assert_called_once()

    @patch('apps.core.mfa.MFASettings')
    @patch('apps.core.mfa.MFAManager._send_otp_email')
    def test_email_setup_no_email_returns_error(self, mock_send, MockMFA):
        user = _make_user(email=None)
        mock_settings = MagicMock()
        MockMFA.objects.get_or_create.return_value = (mock_settings, True)

        result = MFAManager.setup_mfa(user, email=None, method=MFAMethod.EMAIL)

        assert 'error' in result
        mock_send.assert_not_called()

    @patch('apps.core.mfa.MFASettings')
    @patch('apps.core.mfa.encrypt_field', return_value='encrypted')
    def test_totp_setup_returns_qr_code(self, mock_encrypt, MockMFA):
        user = _make_user()
        mock_settings = MagicMock()
        MockMFA.objects.get_or_create.return_value = (mock_settings, True)

        result = MFAManager.setup_mfa(user, method=MFAMethod.TOTP)

        assert result['method'] == MFAMethod.TOTP
        assert 'qr_code' in result
        assert 'otpauth_url' in result
        assert result['qr_code'].startswith('data:image/png;base64,')

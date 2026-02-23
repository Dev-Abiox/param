"""
Tests for startup environment validation (apps.core.config.validation).
"""

from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.core.config.validation import validate_required_secrets


# A secret that passes _assert_secret (32+ chars, not a placeholder)
GOOD_SECRET = "a" * 32
SHORT_SECRET = "short"
_WARN_PATH = "apps.core.config.validation._warn_if_missing"


class TestDevEnvironment:
    """In dev mode, validation should warn but not raise."""

    def test_dev_does_not_raise_on_empty_secrets(self):
        # Should not raise — dev is lenient
        validate_required_secrets("dev", "", "", "")

    def test_dev_does_not_raise_on_placeholder(self):
        validate_required_secrets("dev", "change-me", "test", "default")


class TestProductionCoreSecrets:
    """In production, core secrets must be strong."""

    def test_missing_secret_key_raises(self):
        with pytest.raises(ImproperlyConfigured, match="SECRET_KEY"):
            validate_required_secrets(
                "production", "", GOOD_SECRET, GOOD_SECRET,
                razorpay_key_id="key", razorpay_key_secret="sec",
                razorpay_webhook_secret="wh", email_host_user="u",
                email_host_password="p",
            )

    def test_short_secret_key_raises(self):
        with pytest.raises(ImproperlyConfigured, match="SECRET_KEY.*too short"):
            validate_required_secrets(
                "production", SHORT_SECRET, GOOD_SECRET, GOOD_SECRET,
                razorpay_key_id="key", razorpay_key_secret="sec",
                razorpay_webhook_secret="wh", email_host_user="u",
                email_host_password="p",
            )

    def test_placeholder_master_key_raises(self):
        with pytest.raises(ImproperlyConfigured, match="MASTER_ENCRYPTION_KEY"):
            validate_required_secrets(
                "production", GOOD_SECRET, "change-me", GOOD_SECRET,
                razorpay_key_id="key", razorpay_key_secret="sec",
                razorpay_webhook_secret="wh", email_host_user="u",
                email_host_password="p",
            )

    def test_all_good_secrets_passes(self):
        # Should not raise
        validate_required_secrets(
            "production", GOOD_SECRET, GOOD_SECRET, GOOD_SECRET,
            razorpay_key_id="rzp_live_abc", razorpay_key_secret="secret123",
            razorpay_webhook_secret="whsec_123", email_host_user="user@smtp.com",
            email_host_password="smtp_pass",
        )


class TestProductionBillingSecrets:
    """In production, missing Razorpay/email creds warn but do not block startup."""

    def _call_with_billing(self, **overrides):
        defaults = dict(
            razorpay_key_id="rzp_live_abc",
            razorpay_key_secret="secret123",
            razorpay_webhook_secret="whsec_123",
            email_host_user="user@smtp.com",
            email_host_password="smtp_pass",
        )
        defaults.update(overrides)
        validate_required_secrets(
            "production", GOOD_SECRET, GOOD_SECRET, GOOD_SECRET,
            **defaults,
        )

    @patch(_WARN_PATH)
    def test_missing_razorpay_key_id_warns(self, mock_warn):
        self._call_with_billing(razorpay_key_id="")
        mock_warn.assert_any_call("RAZORPAY_KEY_ID", "")

    @patch(_WARN_PATH)
    def test_missing_razorpay_key_secret_warns(self, mock_warn):
        self._call_with_billing(razorpay_key_secret="")
        mock_warn.assert_any_call("RAZORPAY_KEY_SECRET", "")

    @patch(_WARN_PATH)
    def test_missing_razorpay_webhook_secret_warns(self, mock_warn):
        self._call_with_billing(razorpay_webhook_secret="")
        mock_warn.assert_any_call("RAZORPAY_WEBHOOK_SECRET", "")

    @patch(_WARN_PATH)
    def test_missing_email_host_user_warns(self, mock_warn):
        self._call_with_billing(email_host_user="")
        mock_warn.assert_any_call("EMAIL_HOST_USER", "")

    @patch(_WARN_PATH)
    def test_missing_email_host_password_warns(self, mock_warn):
        self._call_with_billing(email_host_password="")
        mock_warn.assert_any_call("EMAIL_HOST_PASSWORD", "")

    @patch(_WARN_PATH)
    def test_placeholder_razorpay_key_warns(self, mock_warn):
        self._call_with_billing(razorpay_key_id="change-me")
        mock_warn.assert_any_call("RAZORPAY_KEY_ID", "change-me")

    @patch(_WARN_PATH)
    def test_staging_also_warns(self, mock_warn):
        """Staging should warn (same as production) but not raise."""
        validate_required_secrets(
            "staging", GOOD_SECRET, GOOD_SECRET, GOOD_SECRET,
            razorpay_key_id="",
            razorpay_key_secret="sec",
            razorpay_webhook_secret="wh",
            email_host_user="u",
            email_host_password="p",
        )
        mock_warn.assert_any_call("RAZORPAY_KEY_ID", "")

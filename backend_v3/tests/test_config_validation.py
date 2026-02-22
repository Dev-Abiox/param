"""
Tests for startup environment validation (apps.core.config.validation).
"""

import pytest
from django.core.exceptions import ImproperlyConfigured

from apps.core.config.validation import validate_required_secrets


# A secret that passes _assert_secret (32+ chars, not a placeholder)
GOOD_SECRET = "a" * 32
SHORT_SECRET = "short"


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
    """In production, Razorpay and email credentials must be present."""

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

    def test_missing_razorpay_key_id_raises(self):
        with pytest.raises(ImproperlyConfigured, match="RAZORPAY_KEY_ID"):
            self._call_with_billing(razorpay_key_id="")

    def test_missing_razorpay_key_secret_raises(self):
        with pytest.raises(ImproperlyConfigured, match="RAZORPAY_KEY_SECRET"):
            self._call_with_billing(razorpay_key_secret="")

    def test_missing_razorpay_webhook_secret_raises(self):
        with pytest.raises(ImproperlyConfigured, match="RAZORPAY_WEBHOOK_SECRET"):
            self._call_with_billing(razorpay_webhook_secret="")

    def test_missing_email_host_user_raises(self):
        with pytest.raises(ImproperlyConfigured, match="EMAIL_HOST_USER"):
            self._call_with_billing(email_host_user="")

    def test_missing_email_host_password_raises(self):
        with pytest.raises(ImproperlyConfigured, match="EMAIL_HOST_PASSWORD"):
            self._call_with_billing(email_host_password="")

    def test_placeholder_razorpay_key_raises(self):
        with pytest.raises(ImproperlyConfigured, match="RAZORPAY_KEY_ID"):
            self._call_with_billing(razorpay_key_id="change-me")

    def test_staging_also_validates(self):
        """Staging should enforce the same checks as production."""
        with pytest.raises(ImproperlyConfigured, match="RAZORPAY_KEY_ID"):
            validate_required_secrets(
                "staging", GOOD_SECRET, GOOD_SECRET, GOOD_SECRET,
                razorpay_key_id="",
                razorpay_key_secret="sec",
                razorpay_webhook_secret="wh",
                email_host_user="u",
                email_host_password="p",
            )

"""
Startup environment validation.

Called at the bottom of settings.py to fail fast if any required secret is
missing or left at an insecure default value.  The application must not start
with placeholder keys because PHI encryption, audit signing, and JWT integrity
all depend on strong, unique secrets.
"""

from django.core.exceptions import ImproperlyConfigured

# Minimum acceptable length for secret keys (bytes of entropy).
MIN_KEY_LENGTH = 32

# Values that are never allowed in production (common developer placeholders).
FORBIDDEN_VALUES = {
    "",
    "change-me-in-production",
    "change-me",
    "secret",
    "insecure",
    "development",
    "test",
    "default",
    "please-change-me",
}


def validate_required_secrets(env: str, secret_key: str, master_key: str, audit_key: str) -> None:
    """
    Assert that all secrets are present and not insecure defaults.

    :param env:        APP_ENV value ('dev', 'staging', 'production').
    :param secret_key: Django SECRET_KEY.
    :param master_key: PHI MASTER_ENCRYPTION_KEY.
    :param audit_key:  Audit-chain AUDIT_SIGNING_KEY.
    :raises ImproperlyConfigured: on the first validation failure.
    """
    # Skip strict validation in local dev so developers can run without .env
    if env not in ("production", "prod", "staging"):
        _warn_if_insecure("SECRET_KEY", secret_key)
        _warn_if_insecure("MASTER_ENCRYPTION_KEY", master_key)
        _warn_if_insecure("AUDIT_SIGNING_KEY", audit_key)
        return

    _assert_secret("SECRET_KEY", secret_key)
    _assert_secret("MASTER_ENCRYPTION_KEY", master_key)
    _assert_secret("AUDIT_SIGNING_KEY", audit_key)


def _assert_secret(name: str, value: str) -> None:
    """Raise ImproperlyConfigured if *value* is absent or insecure."""
    if not value or value.strip().lower() in FORBIDDEN_VALUES:
        raise ImproperlyConfigured(
            f"[Security] {name} must be set to a strong secret in production. "
            f"Current value is missing or a known placeholder."
        )
    if len(value) < MIN_KEY_LENGTH:
        raise ImproperlyConfigured(
            f"[Security] {name} is too short ({len(value)} chars). "
            f"Minimum required: {MIN_KEY_LENGTH} characters."
        )


def _warn_if_insecure(name: str, value: str) -> None:
    """Log a warning (not an error) in non-production environments."""
    import logging
    log = logging.getLogger(__name__)
    if not value or value.strip().lower() in FORBIDDEN_VALUES:
        log.warning(
            "[Security] %s is missing or using an insecure default. "
            "This is only acceptable in a local dev environment.",
            name,
        )

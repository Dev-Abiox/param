"""
MFA (Multi-Factor Authentication) module for Clinomic Platform.

Provides Email OTP-based MFA with backup codes.
"""

import hashlib
import random
import secrets
from datetime import datetime, timezone
from typing import Optional

from django.conf import settings
from django.core.cache import cache

from .models import MFAMethod, MFASettings, User

# Cache key templates
_OTP_CACHE_KEY = 'mfa_otp:{user_id}'
_OTP_COOLDOWN_KEY = 'mfa_otp_cooldown:{user_id}'
_OTP_TTL = 300        # 5 minutes
_OTP_COOLDOWN = 60    # 60 seconds between resends


def _mask_email(email: str) -> str:
    """Mask an email address for display: j***@gmail.com"""
    if not email or '@' not in email:
        return '***'
    local, domain = email.rsplit('@', 1)
    if len(local) <= 1:
        masked_local = '*'
    else:
        masked_local = local[0] + '***'
    return f'{masked_local}@{domain}'


class MFAManager:
    """
    Manages MFA setup, verification, and backup codes.
    Uses Email OTP exclusively.
    """

    @staticmethod
    def is_mfa_required(user: User) -> bool:
        """Check if MFA is required for this user's role."""
        return user.role in settings.MFA_REQUIRED_ROLES

    @staticmethod
    def get_mfa_status(user: User) -> dict:
        """Get MFA status for a user."""
        try:
            mfa_settings = user.mfa_settings
            return {
                'enabled': mfa_settings.is_enabled,
                'verified': mfa_settings.verified_at is not None,
                'recovery_email': bool(mfa_settings.recovery_email),
                'backup_codes_remaining': len([c for c in mfa_settings.backup_codes if not c.get('used')]),
                'mfa_method': MFAMethod.EMAIL,
            }
        except MFASettings.DoesNotExist:
            return {
                'enabled': False,
                'verified': False,
                'recovery_email': False,
                'backup_codes_remaining': 0,
                'mfa_method': MFAMethod.EMAIL,
            }

    @staticmethod
    def setup_mfa(user: User, email: Optional[str] = None, method: str = MFAMethod.EMAIL) -> dict:
        """
        Initialize MFA setup for a user (always uses Email OTP).

        Args:
            user: The user to set up MFA for.
            email: Recovery email (also used as OTP destination).
            method: Ignored — always uses EMAIL.

        Returns:
            dict with setup data.
        """
        mfa_settings, _ = MFASettings.objects.get_or_create(user=user)
        mfa_settings.mfa_method = MFAMethod.EMAIL
        mfa_settings.recovery_email = email
        mfa_settings.is_enabled = False
        mfa_settings.verified_at = None
        mfa_settings.secret_key = ''

        otp_email = email or user.email
        if not otp_email:
            return {'error': 'Email address is required for email OTP'}

        mfa_settings.save()

        # Generate and send OTP for setup verification
        code = MFAManager.generate_email_otp(user)
        MFAManager._send_otp_email(user, code, otp_email)

        return {
            'method': MFAMethod.EMAIL,
            'email_masked': _mask_email(otp_email),
        }

    @staticmethod
    def verify_setup(user: User, code: str) -> dict:
        """
        Verify MFA setup with an email OTP code.

        Returns:
            dict with 'success', 'backup_codes' (only on first setup)
        """
        try:
            mfa_settings = user.mfa_settings
        except MFASettings.DoesNotExist:
            return {'success': False, 'error': 'MFA not initialized'}

        if not MFAManager.verify_email_otp(user, code):
            return {'success': False, 'error': 'Invalid or expired code'}

        # Generate backup codes on first verification
        backup_codes = []
        if not mfa_settings.is_enabled:
            backup_codes = MFAManager._generate_backup_codes()
            mfa_settings.backup_codes = [
                {'hash': hashlib.sha256(c.encode()).hexdigest(), 'used': False}
                for c in backup_codes
            ]

        mfa_settings.is_enabled = True
        mfa_settings.verified_at = datetime.now(timezone.utc)
        mfa_settings.save()

        return {
            'success': True,
            'backup_codes': backup_codes if backup_codes else None,
        }

    @staticmethod
    def verify_code(user: User, code: str) -> bool:
        """
        Verify an MFA code for login (email OTP or backup code).
        """
        try:
            mfa_settings = user.mfa_settings
        except MFASettings.DoesNotExist:
            return False

        if not mfa_settings.is_enabled:
            return False

        # Try email OTP verification first
        if MFAManager.verify_email_otp(user, code):
            return True

        # Try backup codes
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        for backup in mfa_settings.backup_codes:
            if backup['hash'] == code_hash and not backup['used']:
                backup['used'] = True
                mfa_settings.save()
                return True

        return False

    @staticmethod
    def disable_mfa(user: User, code: str) -> dict:
        """
        Disable MFA for a user (requires valid code).
        """
        if not MFAManager.verify_code(user, code):
            return {'success': False, 'error': 'Invalid code'}

        try:
            mfa_settings = user.mfa_settings
            mfa_settings.is_enabled = False
            mfa_settings.secret_key = ''
            mfa_settings.backup_codes = []
            mfa_settings.verified_at = None
            mfa_settings.mfa_method = MFAMethod.EMAIL
            mfa_settings.save()
            return {'success': True}
        except MFASettings.DoesNotExist:
            return {'success': False, 'error': 'MFA not configured'}

    @staticmethod
    def regenerate_backup_codes(user: User, code: str) -> dict:
        """
        Generate new backup codes (requires valid email OTP).
        """
        try:
            mfa_settings = user.mfa_settings
        except MFASettings.DoesNotExist:
            return {'success': False, 'error': 'MFA not configured'}

        if not MFAManager.verify_email_otp(user, code):
            return {'success': False, 'error': 'Invalid or expired code'}

        backup_codes = MFAManager._generate_backup_codes()
        mfa_settings.backup_codes = [
            {'hash': hashlib.sha256(c.encode()).hexdigest(), 'used': False}
            for c in backup_codes
        ]
        mfa_settings.save()

        return {'success': True, 'backup_codes': backup_codes}

    # ── Email OTP helpers ────────────────────────────────────────────────

    @staticmethod
    def generate_email_otp(user: User) -> str:
        """Generate a 6-digit OTP and store it in cache with 5-min TTL."""
        code = f'{random.SystemRandom().randint(0, 999999):06d}'
        cache_key = _OTP_CACHE_KEY.format(user_id=user.id)
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        cache.set(cache_key, code_hash, timeout=_OTP_TTL)

        # Set cooldown to prevent resend spam
        cooldown_key = _OTP_COOLDOWN_KEY.format(user_id=user.id)
        cache.set(cooldown_key, True, timeout=_OTP_COOLDOWN)

        return code

    @staticmethod
    def verify_email_otp(user: User, code: str) -> bool:
        """Verify email OTP against cached value. Deletes on success."""
        cache_key = _OTP_CACHE_KEY.format(user_id=user.id)
        stored_hash = cache.get(cache_key)
        if not stored_hash:
            return False

        code_hash = hashlib.sha256(code.encode()).hexdigest()
        if code_hash == stored_hash:
            cache.delete(cache_key)
            return True
        return False

    @staticmethod
    def can_resend_otp(user: User) -> bool:
        """Check if the cooldown period has elapsed for resending OTP."""
        cooldown_key = _OTP_COOLDOWN_KEY.format(user_id=user.id)
        return not cache.get(cooldown_key)

    @staticmethod
    def get_otp_email(user: User) -> Optional[str]:
        """Get the email address to send OTP to."""
        try:
            mfa_settings = user.mfa_settings
            return mfa_settings.recovery_email or user.email
        except MFASettings.DoesNotExist:
            return user.email

    @staticmethod
    def _send_otp_email(user: User, code: str, email: str) -> None:
        """Send OTP via Celery email task."""
        from apps.billing.tasks import send_mfa_otp_email
        send_mfa_otp_email.delay(str(user.id), code, email)

    @staticmethod
    def _generate_backup_codes(count: int = 10) -> list[str]:
        """Generate cryptographically secure backup codes."""
        return [secrets.token_hex(8).upper() for _ in range(count)]

    @staticmethod
    def migrate_totp_to_email(user: User) -> None:
        """Auto-migrate a TOTP user to EMAIL method."""
        try:
            mfa_settings = user.mfa_settings
            if mfa_settings.mfa_method == MFAMethod.TOTP:
                mfa_settings.mfa_method = MFAMethod.EMAIL
                mfa_settings.secret_key = ''
                mfa_settings.save(update_fields=['mfa_method', 'secret_key', 'updated_at'])
        except MFASettings.DoesNotExist:
            pass

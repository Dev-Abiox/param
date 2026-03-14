"""
MFA (Multi-Factor Authentication) module for Clinomic Platform.

Provides TOTP-based MFA and Email OTP with backup codes.
"""

import base64
import hashlib
import io
import random
import secrets
from datetime import datetime, timezone
from typing import Optional

import pyotp
import qrcode
from django.conf import settings
from django.core.cache import cache

from .crypto import decrypt_field, encrypt_field
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
    Supports TOTP (authenticator app) and EMAIL (email OTP) methods.
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
                'mfa_method': mfa_settings.mfa_method,
            }
        except MFASettings.DoesNotExist:
            return {
                'enabled': False,
                'verified': False,
                'recovery_email': False,
                'backup_codes_remaining': 0,
                'mfa_method': MFAMethod.TOTP,
            }

    @staticmethod
    def setup_mfa(user: User, email: Optional[str] = None, method: str = MFAMethod.TOTP) -> dict:
        """
        Initialize MFA setup for a user.

        Args:
            user: The user to set up MFA for.
            email: Recovery email (also used as OTP destination for EMAIL method).
            method: 'TOTP' or 'EMAIL'.

        Returns:
            dict with setup data (varies by method).
        """
        mfa_settings, _ = MFASettings.objects.get_or_create(user=user)
        mfa_settings.mfa_method = method
        mfa_settings.recovery_email = email
        mfa_settings.is_enabled = False
        mfa_settings.verified_at = None

        if method == MFAMethod.EMAIL:
            # For email OTP, we don't need a TOTP secret
            otp_email = email or user.email
            if not otp_email:
                return {'error': 'Email address is required for email OTP'}

            mfa_settings.secret_key = ''
            mfa_settings.save()

            # Generate and send OTP for setup verification
            code = MFAManager.generate_email_otp(user)
            MFAManager._send_otp_email(user, code, otp_email)

            return {
                'method': MFAMethod.EMAIL,
                'email_masked': _mask_email(otp_email),
            }
        else:
            # TOTP setup — generate secret and QR code
            secret = pyotp.random_base32()
            mfa_settings.secret_key = encrypt_field(secret)
            mfa_settings.save()

            totp = pyotp.TOTP(secret)
            otpauth_url = totp.provisioning_uri(
                name=user.username,
                issuer_name=settings.MFA_ISSUER_NAME
            )

            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(otpauth_url)
            qr.make(fit=True)

            img = qr.make_image(fill_color='black', back_color='white')
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            qr_base64 = base64.b64encode(buffer.getvalue()).decode()

            return {
                'method': MFAMethod.TOTP,
                'secret': secret,
                'qr_code': f'data:image/png;base64,{qr_base64}',
                'otpauth_url': otpauth_url,
            }

    @staticmethod
    def verify_setup(user: User, code: str) -> dict:
        """
        Verify MFA setup with a code (TOTP or email OTP depending on method).

        Returns:
            dict with 'success', 'backup_codes' (only on first setup)
        """
        try:
            mfa_settings = user.mfa_settings
        except MFASettings.DoesNotExist:
            return {'success': False, 'error': 'MFA not initialized'}

        if mfa_settings.mfa_method == MFAMethod.EMAIL:
            if not MFAManager.verify_email_otp(user, code):
                return {'success': False, 'error': 'Invalid or expired code'}
        else:
            secret = decrypt_field(mfa_settings.secret_key)
            totp = pyotp.TOTP(secret)
            if not totp.verify(code, valid_window=1):
                return {'success': False, 'error': 'Invalid code'}

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
        Verify an MFA code for login (TOTP or email OTP depending on method).
        Backup codes are always accepted regardless of method.
        """
        try:
            mfa_settings = user.mfa_settings
        except MFASettings.DoesNotExist:
            return False

        if not mfa_settings.is_enabled:
            return False

        # Try method-specific verification first
        if mfa_settings.mfa_method == MFAMethod.EMAIL:
            if MFAManager.verify_email_otp(user, code):
                return True
        else:
            secret = decrypt_field(mfa_settings.secret_key)
            totp = pyotp.TOTP(secret)
            if totp.verify(code, valid_window=1):
                return True

        # Try backup codes (works for both methods)
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
            mfa_settings.mfa_method = MFAMethod.TOTP
            mfa_settings.save()
            return {'success': True}
        except MFASettings.DoesNotExist:
            return {'success': False, 'error': 'MFA not configured'}

    @staticmethod
    def regenerate_backup_codes(user: User, code: str) -> dict:
        """
        Generate new backup codes (requires valid verification code).
        For TOTP: requires TOTP code only (not backup).
        For EMAIL: requires email OTP.
        """
        try:
            mfa_settings = user.mfa_settings
        except MFASettings.DoesNotExist:
            return {'success': False, 'error': 'MFA not configured'}

        if mfa_settings.mfa_method == MFAMethod.EMAIL:
            if not MFAManager.verify_email_otp(user, code):
                return {'success': False, 'error': 'Invalid or expired code'}
        else:
            secret = decrypt_field(mfa_settings.secret_key)
            totp = pyotp.TOTP(secret)
            if not totp.verify(code, valid_window=1):
                return {'success': False, 'error': 'Invalid TOTP code'}

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

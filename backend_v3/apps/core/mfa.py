"""
MFA (Multi-Factor Authentication) module for Clinomic Platform.

Provides TOTP-based MFA with backup codes.
"""

import base64
import hashlib
import io
import secrets
from datetime import datetime, timezone
from typing import Optional

import pyotp
import qrcode
from django.conf import settings

from .crypto import decrypt_field, encrypt_field
from .models import MFASettings, User


class MFAManager:
    """
    Manages MFA setup, verification, and backup codes.
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
            }
        except MFASettings.DoesNotExist:
            return {
                'enabled': False,
                'verified': False,
                'recovery_email': False,
                'backup_codes_remaining': 0,
            }

    @staticmethod
    def setup_mfa(user: User, email: Optional[str] = None) -> dict:
        """
        Initialize MFA setup for a user.

        Returns:
            dict with 'secret' (for backup), 'qr_code' (base64), 'otpauth_url'
        """
        # Generate new secret
        secret = pyotp.random_base32()

        # Create or update MFA settings
        mfa_settings, _ = MFASettings.objects.get_or_create(user=user)
        mfa_settings.secret_key = encrypt_field(secret)
        mfa_settings.recovery_email = email
        mfa_settings.is_enabled = False  # Not enabled until verified
        mfa_settings.verified_at = None
        mfa_settings.save()

        # Generate OTP URL
        totp = pyotp.TOTP(secret)
        otpauth_url = totp.provisioning_uri(
            name=user.username,
            issuer_name=settings.MFA_ISSUER_NAME
        )

        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(otpauth_url)
        qr.make(fit=True)

        img = qr.make_image(fill_color='black', back_color='white')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()

        return {
            'secret': secret,
            'qr_code': f'data:image/png;base64,{qr_base64}',
            'otpauth_url': otpauth_url,
        }

    @staticmethod
    def verify_setup(user: User, code: str) -> dict:
        """
        Verify MFA setup with a TOTP code.

        Returns:
            dict with 'success', 'backup_codes' (only on first setup)
        """
        try:
            mfa_settings = user.mfa_settings
        except MFASettings.DoesNotExist:
            return {'success': False, 'error': 'MFA not initialized'}

        # Decrypt secret and verify
        secret = decrypt_field(mfa_settings.secret_key)
        totp = pyotp.TOTP(secret)

        if not totp.verify(code, valid_window=1):
            return {'success': False, 'error': 'Invalid code'}

        # Generate backup codes on first verification
        backup_codes = []
        if not mfa_settings.is_enabled:
            backup_codes = MFAManager._generate_backup_codes()
            mfa_settings.backup_codes = [
                {'hash': hashlib.sha256(code.encode()).hexdigest(), 'used': False}
                for code in backup_codes
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
        Verify a TOTP code for login.
        """
        try:
            mfa_settings = user.mfa_settings
        except MFASettings.DoesNotExist:
            return False

        if not mfa_settings.is_enabled:
            return False

        # Try TOTP first
        secret = decrypt_field(mfa_settings.secret_key)
        totp = pyotp.TOTP(secret)

        if totp.verify(code, valid_window=1):
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
            mfa_settings.save()
            return {'success': True}
        except MFASettings.DoesNotExist:
            return {'success': False, 'error': 'MFA not configured'}

    @staticmethod
    def regenerate_backup_codes(user: User, code: str) -> dict:
        """
        Generate new backup codes (requires valid TOTP code).
        """
        try:
            mfa_settings = user.mfa_settings
        except MFASettings.DoesNotExist:
            return {'success': False, 'error': 'MFA not configured'}

        # Verify with TOTP only (not backup code)
        secret = decrypt_field(mfa_settings.secret_key)
        totp = pyotp.TOTP(secret)

        if not totp.verify(code, valid_window=1):
            return {'success': False, 'error': 'Invalid TOTP code'}

        # Generate new codes
        backup_codes = MFAManager._generate_backup_codes()
        mfa_settings.backup_codes = [
            {'hash': hashlib.sha256(c.encode()).hexdigest(), 'used': False}
            for c in backup_codes
        ]
        mfa_settings.save()

        return {'success': True, 'backup_codes': backup_codes}

    @staticmethod
    def _generate_backup_codes(count: int = 10) -> list[str]:
        """Generate cryptographically secure backup codes."""
        return [secrets.token_hex(4).upper() for _ in range(count)]

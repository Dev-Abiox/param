"""
Cryptography module for PHI (Protected Health Information) encryption.

Uses Fernet symmetric encryption for field-level data protection.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)

_cipher = None


class CryptoError(Exception):
    """Raised when encryption/decryption fails."""
    pass


def _get_cipher() -> Fernet:
    """Get or initialize the Fernet cipher."""
    global _cipher
    if _cipher is None:
        key = settings.MASTER_ENCRYPTION_KEY
        if not key:
            raise CryptoError("MASTER_ENCRYPTION_KEY not configured")
        try:
            _cipher = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as e:
            logger.error(f"Failed to initialize cipher: {e}")
            raise CryptoError("Invalid encryption key") from e
    return _cipher


def encrypt_field(plaintext: str) -> str:
    """
    Encrypt a plaintext string.

    Args:
        plaintext: The string to encrypt

    Returns:
        Base64-encoded ciphertext

    Raises:
        CryptoError: If encryption fails
    """
    if not plaintext:
        return ""

    try:
        cipher = _get_cipher()
        return cipher.encrypt(plaintext.encode()).decode()
    except CryptoError:
        raise
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        raise CryptoError("Encryption failed") from e


def decrypt_field(ciphertext: str) -> str:
    """
    Decrypt a ciphertext string.

    Args:
        ciphertext: Base64-encoded ciphertext

    Returns:
        Decrypted plaintext

    Raises:
        CryptoError: If decryption fails (fail closed for security)
    """
    if not ciphertext:
        return ""

    try:
        cipher = _get_cipher()
        return cipher.decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        logger.error("Decryption failed - invalid token or key mismatch")
        raise CryptoError("Decryption failed - data may be corrupted or key mismatch")
    except CryptoError:
        raise
    except Exception as e:
        logger.error(f"Decryption error: {e}")
        raise CryptoError("Decryption failed") from e


def encrypt_dict_fields(data: dict, fields: list[str]) -> dict:
    """
    Encrypt specific fields in a dictionary.

    Args:
        data: Dictionary containing fields to encrypt
        fields: List of field names to encrypt

    Returns:
        New dictionary with encrypted fields
    """
    result = dict(data)
    for field in fields:
        if field in result and result[field]:
            result[field] = encrypt_field(str(result[field]))
    return result


def decrypt_dict_fields(data: dict, fields: list[str]) -> dict:
    """
    Decrypt specific fields in a dictionary.

    Args:
        data: Dictionary containing encrypted fields
        fields: List of field names to decrypt

    Returns:
        New dictionary with decrypted fields
    """
    result = dict(data)
    for field in fields:
        if field in result and result[field]:
            result[field] = decrypt_field(str(result[field]))
    return result


def is_crypto_ready() -> bool:
    """Check if encryption is properly configured."""
    try:
        _get_cipher()
        return True
    except CryptoError:
        return False


def get_crypto_status() -> dict:
    """Get encryption status for health checks."""
    return {
        'configured': bool(settings.MASTER_ENCRYPTION_KEY),
        'ready': is_crypto_ready(),
    }

"""
Cryptography module for PHI (Protected Health Information) encryption.

Uses Fernet symmetric encryption for field-level data protection.
Supports MultiFernet key rotation: the primary key (MASTER_ENCRYPTION_KEY)
is used for all new encryption. Previous keys (PREVIOUS_ENCRYPTION_KEYS)
can still decrypt old ciphertext, enabling zero-downtime key rotation.

Key rotation procedure:
  1. Generate a new Fernet key.
  2. Move the current MASTER_ENCRYPTION_KEY value into PREVIOUS_ENCRYPTION_KEYS
     (comma-separated, most-recent first).
  3. Set the new key as MASTER_ENCRYPTION_KEY.
  4. Restart services — old data remains readable, new data uses the new key.
  5. (Optional) Run the `rotate_encryption_keys` management command to
     re-encrypt all records under the new key, then remove old keys.
"""

import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings

logger = logging.getLogger(__name__)

_cipher = None
_primary_fernet = None


class CryptoError(Exception):
    """Raised when encryption/decryption fails."""
    pass


def _get_cipher() -> MultiFernet:
    """Get or initialize the MultiFernet cipher with key rotation support."""
    global _cipher, _primary_fernet
    if _cipher is None:
        key = settings.MASTER_ENCRYPTION_KEY
        if not key:
            raise CryptoError("MASTER_ENCRYPTION_KEY not configured")
        try:
            primary = Fernet(key.encode() if isinstance(key, str) else key)
            _primary_fernet = primary
            fernet_keys = [primary]

            # Load previous keys for decryption of old ciphertext
            previous_keys = getattr(settings, 'PREVIOUS_ENCRYPTION_KEYS', '')
            if previous_keys:
                for old_key in previous_keys.split(','):
                    old_key = old_key.strip()
                    if old_key:
                        fernet_keys.append(
                            Fernet(old_key.encode() if isinstance(old_key, str) else old_key)
                        )

            _cipher = MultiFernet(fernet_keys)
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


def rotate_field(ciphertext: str) -> str | None:
    """
    Re-encrypt a ciphertext under the current primary key.

    Returns the new ciphertext if rotation was needed, or None if the value
    is already encrypted with the primary key (no change needed).

    Raises:
        CryptoError: If decryption or re-encryption fails.
    """
    if not ciphertext:
        return None

    try:
        cipher = _get_cipher()
        rotated = cipher.rotate(ciphertext.encode())
        if rotated == ciphertext.encode():
            return None  # already using current key
        return rotated.decode()
    except InvalidToken:
        logger.error("Key rotation failed - invalid token or key mismatch")
        raise CryptoError("Key rotation failed - data may be corrupted or key mismatch")
    except CryptoError:
        raise
    except Exception as e:
        logger.error(f"Key rotation error: {e}")
        raise CryptoError("Key rotation failed") from e


def is_crypto_ready() -> bool:
    """Check if encryption is properly configured."""
    try:
        _get_cipher()
        return True
    except CryptoError:
        return False


def get_crypto_status() -> dict:
    """Get encryption status for health checks."""
    previous_keys = getattr(settings, 'PREVIOUS_ENCRYPTION_KEYS', '')
    num_previous = len([k for k in previous_keys.split(',') if k.strip()]) if previous_keys else 0
    return {
        'configured': bool(settings.MASTER_ENCRYPTION_KEY),
        'ready': is_crypto_ready(),
        'key_rotation': {
            'previous_keys_loaded': num_previous,
            'rotation_pending': num_previous > 0,
        },
    }

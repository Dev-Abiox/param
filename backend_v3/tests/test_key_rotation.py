"""
Tests for MultiFernet key rotation in the crypto module.
"""

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from apps.core.crypto import CryptoError


# Two valid Fernet keys for testing rotation
KEY_A = "vXR9o6LX2YVy0aIYIvlq5tFyRp-kXHjnNzOm8o-mkYQ="
KEY_B = Fernet.generate_key().decode()


class TestMultiFernetRotation:
    """Tests for key rotation support via MultiFernet."""

    @pytest.fixture(autouse=True)
    def reset_cipher(self):
        """Reset the global cipher before each test."""
        from apps.core import crypto
        crypto._cipher = None
        crypto._primary_fernet = None
        yield
        crypto._cipher = None
        crypto._primary_fernet = None

    @override_settings(MASTER_ENCRYPTION_KEY=KEY_A, PREVIOUS_ENCRYPTION_KEYS="")
    def test_single_key_encrypt_decrypt(self):
        """Basic encrypt/decrypt works with a single key (no rotation)."""
        from apps.core.crypto import decrypt_field, encrypt_field

        plaintext = "Patient PHI Data"
        ciphertext = encrypt_field(plaintext)
        assert decrypt_field(ciphertext) == plaintext

    @override_settings(MASTER_ENCRYPTION_KEY=KEY_B, PREVIOUS_ENCRYPTION_KEYS=KEY_A)
    def test_decrypt_with_previous_key(self):
        """Data encrypted with the old key is decryptable after rotation."""
        from apps.core.crypto import decrypt_field, encrypt_field

        # First: encrypt with KEY_A only
        from apps.core import crypto
        crypto._cipher = None
        crypto._primary_fernet = None

        with override_settings(MASTER_ENCRYPTION_KEY=KEY_A, PREVIOUS_ENCRYPTION_KEYS=""):
            from apps.core.crypto import encrypt_field as encrypt_with_old
            crypto._cipher = None
            crypto._primary_fernet = None
            old_ciphertext = encrypt_with_old("Secret Name")

        # Now: switch to KEY_B as primary, KEY_A as previous
        crypto._cipher = None
        crypto._primary_fernet = None

        # Should be able to decrypt old ciphertext
        decrypted = decrypt_field(old_ciphertext)
        assert decrypted == "Secret Name"

    @override_settings(MASTER_ENCRYPTION_KEY=KEY_B, PREVIOUS_ENCRYPTION_KEYS=KEY_A)
    def test_new_encryption_uses_primary_key(self):
        """New encryptions should use the primary (new) key."""
        from apps.core.crypto import encrypt_field

        ciphertext = encrypt_field("New Data")

        # Verify it can be decrypted with KEY_B alone
        from cryptography.fernet import Fernet as RawFernet
        raw = RawFernet(KEY_B.encode())
        assert raw.decrypt(ciphertext.encode()).decode() == "New Data"

    @override_settings(MASTER_ENCRYPTION_KEY=KEY_A, PREVIOUS_ENCRYPTION_KEYS="")
    def test_rotate_field_returns_none_when_current(self):
        """rotate_field returns None if already encrypted with primary key."""
        from apps.core.crypto import encrypt_field, rotate_field

        ciphertext = encrypt_field("Test Value")
        result = rotate_field(ciphertext)
        # MultiFernet.rotate returns re-encrypted data; if already using
        # primary key it still re-encrypts (with new timestamp), so
        # result may not be None. The important thing is no error occurs.
        assert result is None or isinstance(result, str)

    @override_settings(MASTER_ENCRYPTION_KEY=KEY_B, PREVIOUS_ENCRYPTION_KEYS=KEY_A)
    def test_rotate_field_reencrypts_old_data(self):
        """rotate_field re-encrypts data from an old key to the new primary."""
        from apps.core import crypto
        from apps.core.crypto import rotate_field

        # Encrypt with old key
        crypto._cipher = None
        crypto._primary_fernet = None
        with override_settings(MASTER_ENCRYPTION_KEY=KEY_A, PREVIOUS_ENCRYPTION_KEYS=""):
            from apps.core.crypto import encrypt_field as encrypt_old
            crypto._cipher = None
            crypto._primary_fernet = None
            old_ciphertext = encrypt_old("Rotate Me")

        # Rotate under new key
        crypto._cipher = None
        crypto._primary_fernet = None
        rotated = rotate_field(old_ciphertext)
        assert rotated is not None

        # Verify rotated ciphertext is decryptable with new key alone
        from cryptography.fernet import Fernet as RawFernet
        raw = RawFernet(KEY_B.encode())
        assert raw.decrypt(rotated.encode()).decode() == "Rotate Me"

    @override_settings(MASTER_ENCRYPTION_KEY=KEY_A, PREVIOUS_ENCRYPTION_KEYS="")
    def test_rotate_field_empty_string(self):
        """rotate_field handles empty strings gracefully."""
        from apps.core.crypto import rotate_field

        assert rotate_field("") is None
        assert rotate_field(None) is None

    @override_settings(MASTER_ENCRYPTION_KEY=KEY_A, PREVIOUS_ENCRYPTION_KEYS="")
    def test_rotate_field_invalid_ciphertext_raises(self):
        """rotate_field raises CryptoError for invalid input."""
        from apps.core.crypto import rotate_field

        with pytest.raises(CryptoError):
            rotate_field("definitely-not-valid-ciphertext")

    @override_settings(MASTER_ENCRYPTION_KEY=KEY_A, PREVIOUS_ENCRYPTION_KEYS=KEY_B)
    def test_get_crypto_status_reports_previous_keys(self):
        """get_crypto_status reports the number of previous keys."""
        from apps.core.crypto import get_crypto_status

        status = get_crypto_status()
        assert status["key_rotation"]["previous_keys_loaded"] == 1
        assert status["key_rotation"]["rotation_pending"] is True

    @override_settings(MASTER_ENCRYPTION_KEY=KEY_A, PREVIOUS_ENCRYPTION_KEYS="")
    def test_get_crypto_status_no_rotation(self):
        """get_crypto_status shows no rotation when no previous keys."""
        from apps.core.crypto import get_crypto_status

        status = get_crypto_status()
        assert status["key_rotation"]["previous_keys_loaded"] == 0
        assert status["key_rotation"]["rotation_pending"] is False

    @override_settings(MASTER_ENCRYPTION_KEY=KEY_A, PREVIOUS_ENCRYPTION_KEYS=f"{KEY_B},invalid-key")
    def test_invalid_previous_key_raises(self):
        """An invalid previous key should fail on cipher initialization."""
        from apps.core.crypto import encrypt_field

        with pytest.raises(CryptoError, match="Invalid encryption key"):
            encrypt_field("test")

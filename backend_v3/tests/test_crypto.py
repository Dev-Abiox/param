"""
Tests for the crypto module (PHI encryption/decryption).
"""

import pytest
from unittest.mock import patch

from django.test import override_settings


class TestCryptoModule:
    """Tests for encryption and decryption functions."""

    @pytest.fixture(autouse=True)
    def reset_cipher(self):
        """Reset the global cipher before each test."""
        from apps.core import crypto
        crypto._cipher = None
        yield
        crypto._cipher = None

    @override_settings(MASTER_ENCRYPTION_KEY="dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
    def test_encrypt_field_returns_ciphertext(self):
        """Test that encrypt_field returns non-empty ciphertext."""
        from apps.core.crypto import encrypt_field

        plaintext = "John Doe"
        ciphertext = encrypt_field(plaintext)

        assert ciphertext != ""
        assert ciphertext != plaintext
        assert len(ciphertext) > len(plaintext)

    @override_settings(MASTER_ENCRYPTION_KEY="dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
    def test_decrypt_field_returns_original(self):
        """Test that decrypt_field returns original plaintext."""
        from apps.core.crypto import decrypt_field, encrypt_field

        original = "Patient Name 123"
        ciphertext = encrypt_field(original)
        decrypted = decrypt_field(ciphertext)

        assert decrypted == original

    @override_settings(MASTER_ENCRYPTION_KEY="dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
    def test_encrypt_empty_string_returns_empty(self):
        """Test that encrypting empty string returns empty."""
        from apps.core.crypto import encrypt_field

        result = encrypt_field("")
        assert result == ""

    @override_settings(MASTER_ENCRYPTION_KEY="dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
    def test_decrypt_empty_string_returns_empty(self):
        """Test that decrypting empty string returns empty."""
        from apps.core.crypto import decrypt_field

        result = decrypt_field("")
        assert result == ""

    @override_settings(MASTER_ENCRYPTION_KEY=None)
    def test_encrypt_without_key_raises_error(self):
        """Test that encryption fails without key configured."""
        from apps.core.crypto import CryptoError, encrypt_field

        with pytest.raises(CryptoError, match="not configured"):
            encrypt_field("test")

    @override_settings(MASTER_ENCRYPTION_KEY="dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
    def test_decrypt_invalid_ciphertext_raises_error(self):
        """Test that decrypting invalid data raises error (fail-closed)."""
        from apps.core.crypto import CryptoError, decrypt_field

        with pytest.raises(CryptoError):
            decrypt_field("invalid-ciphertext-data")

    @override_settings(MASTER_ENCRYPTION_KEY="dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
    def test_encrypt_dict_fields(self):
        """Test encrypting specific fields in a dictionary."""
        from apps.core.crypto import decrypt_field, encrypt_dict_fields

        data = {"name": "John Doe", "age": 45, "ssn": "123-45-6789"}
        encrypted = encrypt_dict_fields(data, ["name", "ssn"])

        # Original should be unchanged
        assert data["name"] == "John Doe"

        # Encrypted fields should be different
        assert encrypted["name"] != "John Doe"
        assert encrypted["ssn"] != "123-45-6789"

        # Non-encrypted fields should be same
        assert encrypted["age"] == 45

        # Should be decryptable
        assert decrypt_field(encrypted["name"]) == "John Doe"

    @override_settings(MASTER_ENCRYPTION_KEY="dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
    def test_is_crypto_ready_with_valid_key(self):
        """Test is_crypto_ready returns True with valid key."""
        from apps.core.crypto import is_crypto_ready

        assert is_crypto_ready() is True

    @override_settings(MASTER_ENCRYPTION_KEY=None)
    def test_is_crypto_ready_without_key(self):
        """Test is_crypto_ready returns False without key."""
        from apps.core.crypto import is_crypto_ready

        assert is_crypto_ready() is False

    @override_settings(MASTER_ENCRYPTION_KEY="dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
    def test_get_crypto_status(self):
        """Test crypto status reporting."""
        from apps.core.crypto import get_crypto_status

        status = get_crypto_status()

        assert "configured" in status
        assert "ready" in status
        assert status["configured"] is True
        assert status["ready"] is True

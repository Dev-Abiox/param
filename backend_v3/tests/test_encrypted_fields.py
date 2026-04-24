"""
Tests for EncryptedTextField / EncryptedJSONField custom model fields (P0-4).
"""

import json

import pytest


# Known-good Fernet key for tests.
_TEST_KEY = 'vXR9o6LX2YVy0aIYIvlq5tFyRp-kXHjnNzOm8o-mkYQ='


@pytest.fixture(autouse=True)
def _reset_cipher():
    from apps.core import crypto
    crypto._cipher = None
    yield
    crypto._cipher = None


class TestEncryptedTextField:
    @pytest.fixture(autouse=True)
    def _keyed(self, settings):
        settings.MASTER_ENCRYPTION_KEY = _TEST_KEY
        yield
    def test_encrypts_on_prep(self):
        from apps.core.fields import EncryptedTextField

        f = EncryptedTextField()
        prepared = f.get_prep_value('razorpay-webhook-secret')
        assert prepared != 'razorpay-webhook-secret'
        assert prepared.startswith('gAAAAA')

    def test_roundtrip_through_db(self):
        from apps.core.fields import EncryptedTextField

        f = EncryptedTextField()
        ct = f.get_prep_value('super-secret-value')
        pt = f.from_db_value(ct, None, None)
        assert pt == 'super-secret-value'

    def test_empty_string_passthrough(self):
        from apps.core.fields import EncryptedTextField

        f = EncryptedTextField()
        assert f.get_prep_value('') == ''
        assert f.from_db_value('', None, None) == ''

    def test_none_passthrough(self):
        from apps.core.fields import EncryptedTextField

        f = EncryptedTextField()
        assert f.get_prep_value(None) is None
        assert f.from_db_value(None, None, None) is None

    def test_idempotent_on_already_ciphertext(self):
        from apps.core.fields import EncryptedTextField

        f = EncryptedTextField()
        ct = f.get_prep_value('x')
        # Calling prep again on ciphertext must NOT double-encrypt.
        ct_again = f.get_prep_value(ct)
        assert ct_again == ct

    def test_legacy_plaintext_passthrough(self):
        """If a row has legacy plaintext (pre-migration), from_db_value
        returns it as-is so reads keep working during rollout."""
        from apps.core.fields import EncryptedTextField

        f = EncryptedTextField()
        assert f.from_db_value('legacy-plaintext', None, None) == 'legacy-plaintext'


class TestEncryptedJSONField:
    @pytest.fixture(autouse=True)
    def _keyed(self, settings):
        settings.MASTER_ENCRYPTION_KEY = _TEST_KEY
        yield
    def test_dict_roundtrip(self):
        from apps.core.fields import EncryptedJSONField

        f = EncryptedJSONField()
        data = {'Hb': 11.2, 'MCV': 102.3, 'Sex': 'F', 'Age': 45}
        ct = f.get_prep_value(data)
        assert ct.startswith('gAAAAA')
        restored = f.from_db_value(ct, None, None)
        assert restored == data

    def test_list_roundtrip(self):
        from apps.core.fields import EncryptedJSONField

        f = EncryptedJSONField()
        data = [{'fired': 'r1'}, {'fired': 'r2'}]
        ct = f.get_prep_value(data)
        restored = f.from_db_value(ct, None, None)
        assert restored == data

    def test_none_passthrough(self):
        from apps.core.fields import EncryptedJSONField

        f = EncryptedJSONField()
        assert f.get_prep_value(None) is None
        assert f.from_db_value(None, None, None) is None

    def test_empty_string_yields_empty_dict(self):
        from apps.core.fields import EncryptedJSONField

        f = EncryptedJSONField()
        assert f.from_db_value('', None, None) == {}

    def test_legacy_json_string_passthrough(self):
        """Legacy rows storing JSON as plaintext should decode cleanly."""
        from apps.core.fields import EncryptedJSONField

        f = EncryptedJSONField()
        raw = json.dumps({'legacy': True})
        restored = f.from_db_value(raw, None, None)
        assert restored == {'legacy': True}

    def test_idempotent_on_already_ciphertext(self):
        from apps.core.fields import EncryptedJSONField

        f = EncryptedJSONField()
        ct = f.get_prep_value({'a': 1})
        again = f.get_prep_value(ct)
        assert again == ct

    def test_handles_numpy_like_via_default(self):
        """get_prep_value uses default=str so non-JSON-native types serialise."""
        from apps.core.fields import EncryptedJSONField
        from decimal import Decimal

        f = EncryptedJSONField()
        ct = f.get_prep_value({'amount': Decimal('1.25'), 'ok': True})
        restored = f.from_db_value(ct, None, None)
        # Decimal serialises to str
        assert restored == {'amount': '1.25', 'ok': True}

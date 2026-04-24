"""
Custom Django model fields with transparent Fernet encryption.

Used for PHI and secrets that must be encrypted at rest but still feel like
native Django fields to the ORM and to business code.

Two field classes are provided:

  - EncryptedTextField     — stores a single string encrypted at rest.
  - EncryptedJSONField     — stores an arbitrary JSON-serialisable value
                              encrypted at rest.  The DB column is TEXT.

Both fields:

  - Store ciphertext in the database as a plain ``TextField`` column.
  - Encrypt on ``get_prep_value`` (write) using the primary key loaded
    from settings.MASTER_ENCRYPTION_KEY via :mod:`apps.core.crypto`.
  - Decrypt on ``from_db_value`` (read), falling back to treating the
    stored value as plaintext if it does not parse as a Fernet token —
    this is the migration-safe branch so existing rows keep working
    during a zero-downtime rollout.
  - Never index the ciphertext (``db_index`` is forced to False).

Values in memory are always the plaintext form (``str`` for
EncryptedTextField, any JSON-able Python object for
EncryptedJSONField); application code does not see ciphertext.

Do **not** use these fields for values you need to filter on with
``.filter(field=value)`` — the ciphertext is non-deterministic, so
equality queries on the column will never match.  Store a separate
denormalised column (hash, bucket, code) if you need filterability.
"""

import json
import logging

from django.db import models

from apps.core.crypto import CryptoError, decrypt_field, encrypt_field

logger = logging.getLogger(__name__)


def _looks_like_fernet_token(value: str) -> bool:
    """Cheap heuristic: Fernet tokens begin with ``gAAAAA`` after URL-safe
    base64 encoding of the version byte ``0x80``.  Not a guarantee, but
    avoids trying to Fernet-decode obvious plaintext during rollout.
    """
    return isinstance(value, str) and value.startswith('gAAAAA')


class EncryptedTextField(models.TextField):
    """TextField that stores its value Fernet-encrypted at rest."""

    description = 'TextField transparently encrypted with Fernet.'

    def __init__(self, *args, **kwargs):
        # Ciphertext is never indexable.
        kwargs['db_index'] = False
        super().__init__(*args, **kwargs)

    # -- Read path ----------------------------------------------------
    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        if _looks_like_fernet_token(value):
            try:
                return decrypt_field(value)
            except CryptoError:
                logger.exception('EncryptedTextField.from_db_value decrypt failed')
                raise
        # Legacy plaintext row — return as-is so rollout keeps working.
        return value

    def to_python(self, value):
        # Called on forms / deserialisation; ciphertext in memory is rare
        # but we handle the round-trip to be safe.
        if value is None or value == '':
            return value
        if _looks_like_fernet_token(value):
            try:
                return decrypt_field(value)
            except CryptoError:
                logger.exception('EncryptedTextField.to_python decrypt failed')
                raise
        return value

    # -- Write path ---------------------------------------------------
    def get_prep_value(self, value):
        if value is None or value == '':
            return value
        if not isinstance(value, str):
            value = str(value)
        if _looks_like_fernet_token(value):
            # Already ciphertext — do not double-encrypt.
            return value
        return encrypt_field(value)


class EncryptedJSONField(models.TextField):
    """JSON-valued field stored as Fernet-encrypted TEXT.

    Unlike Django's built-in :class:`JSONField`, equality and JSON-path
    filters are NOT supported because the DB column holds opaque
    ciphertext.  Use a denormalised column for anything that needs to
    be filtered.
    """

    description = 'JSON stored as Fernet-encrypted TEXT.'

    def __init__(self, *args, **kwargs):
        kwargs['db_index'] = False
        # The underlying column is TEXT, not JSON.
        super().__init__(*args, **kwargs)

    # -- Read path ----------------------------------------------------
    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        if value == '':
            return {}
        if _looks_like_fernet_token(value):
            try:
                plaintext = decrypt_field(value)
            except CryptoError:
                logger.exception('EncryptedJSONField.from_db_value decrypt failed')
                raise
            try:
                return json.loads(plaintext)
            except json.JSONDecodeError:
                logger.exception('EncryptedJSONField JSON parse failed after decrypt')
                raise
        # Legacy plaintext JSON row (string) — parse and return.
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # Assume Django already parsed the value (e.g. JSONField
            # mid-migration) — return as-is.
            return value

    def to_python(self, value):
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        return self.from_db_value(value, None, None)

    # -- Write path ---------------------------------------------------
    def get_prep_value(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            # Treat a string as either ciphertext or already-JSON.
            if _looks_like_fernet_token(value):
                return value
            try:
                json.loads(value)  # validate
                plaintext = value
            except json.JSONDecodeError:
                plaintext = json.dumps(value)
        else:
            plaintext = json.dumps(value, default=str, sort_keys=True)
        return encrypt_field(plaintext)

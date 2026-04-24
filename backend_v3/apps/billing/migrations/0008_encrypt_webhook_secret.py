"""P0-4 — encrypt WebhookEndpoint.secret at rest.

Alters WebhookEndpoint.secret from a plain CharField to EncryptedTextField
(Fernet ciphertext) and re-encrypts any existing rows that still hold
plaintext secrets.

Legacy plaintext rows keep working after this migration because
EncryptedTextField.from_db_value returns non-Fernet-token values as-is;
however, after this migration runs, all persisted rows are ciphertext so
that property is relied on only during rollout.
"""

import apps.billing.models
import apps.core.fields
from django.db import migrations


def _encrypt_existing_rows(apps_registry, schema_editor):
    """Re-encrypt any existing WebhookEndpoint.secret rows that are still
    plaintext (i.e. do not look like a Fernet token).
    """
    from apps.core.crypto import encrypt_field
    from apps.core.fields import _looks_like_fernet_token

    WebhookEndpoint = apps_registry.get_model('billing', 'WebhookEndpoint')
    for row in WebhookEndpoint.objects.all().only('id', 'secret'):
        if row.secret and not _looks_like_fernet_token(row.secret):
            row.secret = encrypt_field(row.secret)
            row.save(update_fields=['secret'])


def _noop_reverse(apps_registry, schema_editor):
    """Reverse is a no-op — we never attempt to downgrade ciphertext back
    to plaintext automatically.  A manual rotation is required if you
    need to revert, and no production flow should ever want that.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0007_set_live_razorpay_plan_ids'),
    ]

    operations = [
        migrations.AlterField(
            model_name='webhookendpoint',
            name='secret',
            field=apps.core.fields.EncryptedTextField(
                default=apps.billing.models._default_webhook_secret,
                help_text='HMAC-SHA256 signing secret.  Shown once at creation time.',
            ),
        ),
        migrations.RunPython(_encrypt_existing_rows, reverse_code=_noop_reverse),
    ]

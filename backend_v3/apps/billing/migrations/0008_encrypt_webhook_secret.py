"""P0-4 — encrypt WebhookEndpoint.secret at rest (schema only).

Schema-level change: switches the ``secret`` column to
EncryptedTextField (still a TEXT column underneath) so that any *new*
write is Fernet-encrypted by the field's ``get_prep_value``.

Backfill of existing plaintext rows is deliberately NOT performed
inside this migration — iterating and re-encrypting rows during
``migrate_schemas`` at container startup is a failure mode that can
break production deploys on larger datasets.  Instead, run the
one-shot management command at a chosen maintenance window::

    python manage.py encrypt_plaintext_columns --webhook-secrets

EncryptedTextField.from_db_value transparently falls back to treating
non-Fernet-token values as plaintext on read, so the legacy rows keep
working until the backfill runs.
"""

import apps.billing.models
import apps.core.fields
from django.db import migrations


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
    ]

"""Add WebhookEndpoint model for tenant-configured outbound event notifications."""

import uuid
import django.db.models.deletion
from django.db import migrations, models

import apps.billing.models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0003_api_key'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='WebhookEndpoint',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('url', models.URLField(
                    max_length=500,
                    help_text='The HTTPS URL that will receive POST requests for subscribed events.',
                )),
                ('events', models.JSONField(
                    default=list,
                    help_text=(
                        'List of event names this endpoint is subscribed to.  '
                        'Valid values: "screening.completed", "screening.high_risk", '
                        '"consent.revoked", "subscription.changed".'
                    ),
                )),
                ('secret', models.CharField(
                    max_length=64,
                    default=apps.billing.models._default_webhook_secret,
                    help_text='HMAC-SHA256 signing secret.  Shown once at creation time.',
                )),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='webhook_endpoints',
                    to='core.organization',
                )),
            ],
            options={
                'db_table': 'billing_webhook_endpoints',
                'ordering': ['-created_at'],
            },
        ),
    ]

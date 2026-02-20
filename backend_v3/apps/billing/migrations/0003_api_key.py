"""Add APIKey model for programmatic platform access."""

import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0002_add_razorpay_sub_id_index'),
        ('core', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='APIKey',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(
                    help_text='Human-readable label for this key (e.g. "CI Pipeline").',
                    max_length=100,
                )),
                ('key_hash', models.CharField(
                    help_text='SHA-256 hex digest of the raw key — never store the raw key.',
                    max_length=64,
                    unique=True,
                )),
                ('scopes', models.JSONField(
                    default=list,
                    help_text=(
                        'List of granted permission scopes. '
                        'Valid values: "screening:read", "screening:write", "analytics:read".'
                    ),
                )),
                ('rate_limit', models.IntegerField(
                    default=60,
                    help_text='Maximum requests per minute allowed for this key.',
                )),
                ('is_active', models.BooleanField(default=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='api_keys',
                    to='core.organization',
                )),
                ('created_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='created_api_keys',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'billing_api_keys',
                'ordering': ['-created_at'],
            },
        ),
    ]

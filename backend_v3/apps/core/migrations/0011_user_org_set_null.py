"""
Change User.organization on_delete from CASCADE to SET_NULL.

Preserves user records (and audit history) when an Organization is deleted
via the platform admin panel.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_trusteddevice'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='organization',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='users',
                to='core.organization',
            ),
        ),
    ]

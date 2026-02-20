"""
Migration: Rename notification index to Django auto-generated name.

The Notification model's Meta.indexes entry lost its explicit name='notif_user_read_idx',
so Django's migration autodetector wants to rename it to the auto-generated name.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_alter_mfasettings_secret_key'),
    ]

    operations = [
        migrations.RenameIndex(
            model_name='notification',
            new_name='notificatio_user_id_a4dd5c_idx',
            old_name='notif_user_read_idx',
        ),
    ]

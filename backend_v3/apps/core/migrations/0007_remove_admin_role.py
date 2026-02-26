"""
Data migration: merge ADMIN role into LAB.

1. Convert all existing ADMIN users to LAB role.
2. Update the role field choices to remove ADMIN.
"""

from django.db import migrations, models


def migrate_admin_to_lab(apps, schema_editor):
    User = apps.get_model('core', 'User')
    updated = User.objects.filter(role='ADMIN').update(role='LAB')
    if updated:
        print(f"\n  Migrated {updated} ADMIN user(s) to LAB role.")


def reverse_migration(apps, schema_editor):
    # No automatic reversal — cannot distinguish which LAB users were originally ADMIN.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_super_admin_role'),
    ]

    operations = [
        # Step 1: Convert existing ADMIN users → LAB
        migrations.RunPython(migrate_admin_to_lab, reverse_migration),

        # Step 2: Update role field choices (remove ADMIN)
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('SUPER_ADMIN', 'Platform Administrator'),
                    ('LAB', 'Lab Manager'),
                    ('DOCTOR', 'Doctor'),
                ],
                default='LAB',
                max_length=20,
            ),
        ),
    ]

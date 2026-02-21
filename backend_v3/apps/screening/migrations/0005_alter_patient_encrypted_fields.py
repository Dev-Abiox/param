"""
Migration: Remove default='' from age_encrypted and sex_encrypted on Patient.

These fields were added in 0002_encrypt_patient_age_sex with default='' to allow
the data-migration window. The model defines them as plain TextField(blank=True)
without a default, so this migration aligns the migration state with the model.

No database DDL is executed — removing a Python-level default from a TextField
is a no-op at the Postgres level.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0004_bulk_import_job'),
    ]

    operations = [
        migrations.AlterField(
            model_name='patient',
            name='age_encrypted',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='patient',
            name='sex_encrypted',
            field=models.TextField(blank=True),
        ),
    ]

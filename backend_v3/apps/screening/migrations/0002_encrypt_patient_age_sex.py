"""
Migration: encrypt Patient.age and Patient.sex fields.

Steps:
1. Add age_encrypted and sex_encrypted as plain TextFields.
2. Encrypt existing row values into those columns.
3. Drop the old plaintext age and sex columns.

The RunPython step uses apps.core.crypto.encrypt_field so that existing
patient rows are migrated to encrypted storage.  If the MASTER_ENCRYPTION_KEY
is not configured (local dev with no .env), the raw values are stored as
plaintext strings — which is acceptable for development but must not happen
in staging or production (the startup validator blocks startup without the key).
"""

from django.db import migrations, models


def encrypt_existing_age_sex(apps, schema_editor):
    from django.conf import settings
    from apps.core.crypto import encrypt_field, CryptoError

    Patient = apps.get_model('screening', 'Patient')

    key_available = bool(getattr(settings, 'MASTER_ENCRYPTION_KEY', ''))

    for patient in Patient.objects.all():
        if key_available:
            patient.age_encrypted = encrypt_field(str(patient.age))
            patient.sex_encrypted = encrypt_field(str(patient.sex))
        else:
            # Dev fallback: store plaintext (acceptable only without a key)
            patient.age_encrypted = str(patient.age)
            patient.sex_encrypted = str(patient.sex)
        patient.save(update_fields=['age_encrypted', 'sex_encrypted'])


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0001_initial'),
    ]

    operations = [
        # Step 1: Add new encrypted columns (nullable for the data-migration window)
        migrations.AddField(
            model_name='patient',
            name='age_encrypted',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='patient',
            name='sex_encrypted',
            field=models.TextField(blank=True, default=''),
        ),

        # Step 2: Encrypt all existing rows
        migrations.RunPython(encrypt_existing_age_sex, migrations.RunPython.noop),

        # Step 3: Drop the old plaintext columns
        migrations.RemoveField(model_name='patient', name='age'),
        migrations.RemoveField(model_name='patient', name='sex'),
    ]

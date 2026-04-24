"""P0-4 — encrypt Screening.cbc_snapshot at rest.

Adds the new encrypted CBC storage (``cbc_snapshot_enc``) and the
non-PHI denormalised columns (``age_bucket``, ``sex_code``) that let
analytics filter on coarse demographics without JSON-querying the
encrypted blob.  The legacy ``cbc_snapshot`` JSONField stays on the
model for backwards-compat reads of rows written before this release,
but is made optional (``default=dict, blank=True``) so new writes leave
it empty.

The data migration backfills the new fields from every existing row
and blanks out the legacy ``cbc_snapshot`` column so that no plaintext
PHI remains in the database after this migration completes.
"""

from django.db import migrations, models

import apps.core.fields


# Keep in sync with apps.screening.models.age_bucket_for / sex_code_for.
def _age_bucket_for(age):
    if age is None or age == '':
        return ''
    try:
        age_int = int(age)
    except (ValueError, TypeError):
        return ''
    if age_int < 0:
        return ''
    if age_int < 18:
        return 'pediatric'
    if age_int < 40:
        return 'young_adult'
    if age_int < 60:
        return 'middle_aged'
    return 'elderly'


def _sex_code_for(value):
    if value is None or value == '':
        return ''
    v = str(value).strip().upper()
    if v in ('M', 'MALE'):
        return 'M'
    if v in ('F', 'FEMALE'):
        return 'F'
    return ''


def _encrypt_cbc_rows(apps_registry, schema_editor):
    """For every existing Screening row, encrypt cbc_snapshot into
    cbc_snapshot_enc, derive age_bucket + sex_code, and blank the
    legacy plaintext column.

    Uses ``.save(update_fields=[...])`` so the Screening.save() hook
    does not re-run and overwrite our explicit assignments.
    """
    Screening = apps_registry.get_model('screening', 'Screening')
    # Iterate in chunks to bound memory on large tables.
    qs = Screening.objects.all().only(
        'id', 'cbc_snapshot', 'cbc_snapshot_enc', 'age_bucket', 'sex_code'
    )
    for row in qs.iterator(chunk_size=500):
        legacy = row.cbc_snapshot or {}
        if not legacy:
            # No plaintext to migrate.  Leave the denorm cols alone.
            continue
        # Write only if the encrypted column is not already populated.
        if not row.cbc_snapshot_enc:
            row.cbc_snapshot_enc = legacy  # EncryptedJSONField encrypts on save
        if not row.age_bucket:
            row.age_bucket = _age_bucket_for(legacy.get('Age', legacy.get('age')))
        if not row.sex_code:
            row.sex_code = _sex_code_for(legacy.get('Sex', legacy.get('sex')))
        row.cbc_snapshot = {}
        row.save(update_fields=[
            'cbc_snapshot', 'cbc_snapshot_enc', 'age_bucket', 'sex_code'
        ])


def _noop_reverse(apps_registry, schema_editor):
    """Reverse intentionally does not recover plaintext; it would
    require decrypting every row and re-populating the legacy column.
    Run manually if you really need to roll back and have operational
    reasons to expose plaintext PHI — not recommended.
    """


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0011_screening_review_outcome'),
    ]

    operations = [
        migrations.AddField(
            model_name='screening',
            name='cbc_snapshot_enc',
            field=apps.core.fields.EncryptedJSONField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='screening',
            name='age_bucket',
            field=models.CharField(
                blank=True, db_index=True, default='',
                max_length=20,
                choices=[
                    ('pediatric', 'Pediatric (0-17)'),
                    ('young_adult', 'Young Adult (18-39)'),
                    ('middle_aged', 'Middle Aged (40-59)'),
                    ('elderly', 'Elderly (60+)'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='screening',
            name='sex_code',
            field=models.CharField(
                blank=True, db_index=True, default='', max_length=1,
                help_text="Normalised sex code: 'M', 'F', or ''.",
            ),
        ),
        migrations.AlterField(
            model_name='screening',
            name='cbc_snapshot',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(_encrypt_cbc_rows, reverse_code=_noop_reverse),
    ]

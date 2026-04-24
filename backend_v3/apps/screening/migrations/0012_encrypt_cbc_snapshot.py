"""P0-4 — encrypt Screening.cbc_snapshot at rest (schema only).

Schema changes:

  - Add ``cbc_snapshot_enc`` (EncryptedJSONField) — the new encrypted
    storage for the CBC snapshot.  Nullable so this migration can run
    without immediate data movement.
  - Add ``age_bucket`` and ``sex_code`` — denormalised non-PHI columns
    used by analytics filters instead of JSON-path into the encrypted
    blob.
  - Relax ``cbc_snapshot`` to ``default=dict, blank=True`` so new writes
    can leave the legacy column empty.

Backfill of existing rows is deliberately NOT performed inside this
migration.  ``migrate_schemas`` runs at every container start, and a
RunPython that iterates every Screening row per tenant schema and
Fernet-encrypts each in place is a classic source of deploy-time
failures: a single bad row aborts the whole tenant migration and
blocks the container from starting.  Instead, run the one-shot
management command at a chosen maintenance window::

    python manage.py encrypt_plaintext_columns --cbc-snapshots

Until the backfill runs, ``Screening.get_cbc_dict()`` transparently
returns the legacy ``cbc_snapshot`` dict for rows where
``cbc_snapshot_enc`` is still null, and ``Screening.save()`` auto-
migrates cbc_snapshot= assignments into the encrypted column on the
next write.  Analytics views that previously filtered on
``cbc_snapshot__Age/Sex`` now filter on ``age_bucket``/``sex_code``
which will be empty for legacy rows until the backfill runs; the
PopulationCohortsView simply returns empty cohorts for un-backfilled
rows rather than breaking.
"""

from django.db import migrations, models

import apps.core.fields


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
    ]

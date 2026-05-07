"""Add PARTIAL status to BulkImportJob.JobStatus.

Lets the bulk-import task explicitly mark a job as partially successful
(some rows succeeded, some failed) instead of misreporting it as DONE.
The previous code path used a getattr fallback that silently regressed
to DONE when this choice was missing — that defeated the audit fix.

Choices-only change: no schema migration on disk, but Django still
records the metadata change so model state stays consistent.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0014_lab_disclosure_config'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bulkimportjob',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('processing', 'Processing'),
                    ('done', 'Done'),
                    ('partial', 'Partial'),
                    ('failed', 'Failed'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
    ]

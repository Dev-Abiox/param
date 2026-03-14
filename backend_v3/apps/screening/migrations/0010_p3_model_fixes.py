"""
P3 model fixes:
- Doctor.lab: CASCADE → PROTECT (prevent accidental doctor deletion when lab is removed)
- Patient.age_encrypted / sex_encrypted: add null=True alongside blank=True
- BulkImportJob: add index on created_at for efficient status polling
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0009_add_composite_indexes'),
    ]

    operations = [
        # P3-5: Doctor.lab CASCADE → PROTECT
        migrations.AlterField(
            model_name='doctor',
            name='lab',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='doctors',
                to='screening.lab',
            ),
        ),
        # P3-4: Patient encrypted fields — allow NULL
        migrations.AlterField(
            model_name='patient',
            name='age_encrypted',
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='patient',
            name='sex_encrypted',
            field=models.TextField(blank=True, null=True),
        ),
        # P3-3: BulkImportJob created_at index
        migrations.AddIndex(
            model_name='bulkimportjob',
            index=models.Index(fields=['-created_at'], name='bulkimport_created_idx'),
        ),
    ]

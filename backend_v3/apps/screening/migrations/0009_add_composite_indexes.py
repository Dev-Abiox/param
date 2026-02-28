"""
Add composite indexes for work-queue and consent lookups.

- screening_wq_composite_idx: (status, risk_class, -created_at) for WorkQueueView
- consent_patient_status_idx: (patient, status, -consented_at) for consent queries
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0008_fix_patient_unique_together'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='screening',
            index=models.Index(
                fields=['status', 'risk_class', '-created_at'],
                name='screening_wq_composite_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='consent',
            index=models.Index(
                fields=['patient', 'status', '-consented_at'],
                name='consent_patient_status_idx',
            ),
        ),
    ]

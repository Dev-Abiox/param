"""
Migration: Add work-queue status and doctor-review fields to Screening.

Phase 3.2 (LAB Work Queue) + 3.3 (Doctor Review Workflow)
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0002_encrypt_patient_age_sex'),
    ]

    operations = [
        # 3.2 — work queue status
        migrations.AddField(
            model_name='screening',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('in_progress', 'In Progress'),
                    ('completed', 'Completed'),
                ],
                default='pending',
                max_length=20,
            ),
        ),
        # 3.3 — doctor review fields
        migrations.AddField(
            model_name='screening',
            name='is_reviewed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='screening',
            name='clinical_note',
            field=models.TextField(blank=True, default=''),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='screening',
            name='reviewed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='screening',
            name='reviewed_by',
            field=models.CharField(blank=True, default='', max_length=255),
            preserve_default=False,
        ),
        # Index on status for work-queue queries
        migrations.AddIndex(
            model_name='screening',
            index=models.Index(
                fields=['status', '-created_at'],
                name='screening_status_idx',
            ),
        ),
    ]

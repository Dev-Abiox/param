"""
Migration: Add BulkImportJob table for CSV batch screening import (Phase 5.3).
"""

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0003_screening_workflow'),
    ]

    operations = [
        migrations.CreateModel(
            name='BulkImportJob',
            fields=[
                ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ('submitted_by', models.CharField(max_length=255)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('processing', 'Processing'),
                        ('done', 'Done'),
                        ('failed', 'Failed'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('total_rows', models.IntegerField(default=0)),
                ('processed_rows', models.IntegerField(default=0)),
                ('failed_rows', models.IntegerField(default=0)),
                ('error_detail', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'bulk_import_jobs',
                'ordering': ['-created_at'],
            },
        ),
    ]

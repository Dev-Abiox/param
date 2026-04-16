import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='IntegrationEndpoint',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(help_text="Human label, e.g. 'Main Lab Sysmex XN-1000'", max_length=200)),
                ('is_active', models.BooleanField(default=True)),
                ('inbound_format', models.CharField(choices=[('hl7v2', 'HL7 v2.x (ORU/ORM)'), ('fhir_r4', 'FHIR R4 (Observation/DiagnosticReport)'), ('json', 'REST JSON'), ('csv', 'CSV flat file')], default='json', max_length=20)),
                ('outbound_format', models.CharField(choices=[('hl7v2', 'HL7 v2.x (ORU/ORM)'), ('fhir_r4', 'FHIR R4 (Observation/DiagnosticReport)'), ('json', 'REST JSON'), ('csv', 'CSV flat file')], default='json', max_length=20)),
                ('api_key', models.CharField(db_index=True, max_length=64, unique=True)),
                ('callback_url', models.URLField(blank=True, default='')),
                ('callback_headers', models.JSONField(blank=True, default=dict, help_text='Extra HTTP headers for the callback')),
                ('field_mapping', models.JSONField(blank=True, default=dict, help_text='{"lis_field": "clinomic_field"}')),
                ('default_lab_code', models.CharField(blank=True, default='', max_length=50)),
                ('default_doctor_code', models.CharField(blank=True, default='', max_length=50)),
                ('auto_approve', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='IntegrationLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('direction', models.CharField(choices=[('inbound', 'Inbound'), ('outbound', 'Outbound')], max_length=10)),
                ('status', models.CharField(choices=[('success', 'Success'), ('parse_error', 'Parse Error'), ('predict_error', 'Predict Error'), ('callback_error', 'Callback Error')], max_length=20)),
                ('raw_hash', models.CharField(help_text='SHA256 of raw inbound payload', max_length=64)),
                ('mapped_fields', models.JSONField(default=dict, help_text='CBC fields after mapping')),
                ('error_detail', models.TextField(blank=True, default='')),
                ('screening_id', models.UUIDField(blank=True, help_text='Resulting Screening UUID if successful', null=True)),
                ('duration_ms', models.IntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('endpoint', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='integration.integrationendpoint')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='integrationlog',
            index=models.Index(fields=['endpoint', '-created_at'], name='integration_endpoin_e8f2c0_idx'),
        ),
    ]

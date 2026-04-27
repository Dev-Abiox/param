"""Patient PDF Disclosure Spec — per-lab disclosure config fields.

Adds the per-lab placeholder values surfaced on the spec_v1 patient
PDF template (Block E pathologist sign-off + Block F lab grievance
contact + DPDP privacy notice URL).

All fields default to ``''`` so the PDF renderer can fall back to
``[TBD]`` text when a lab has not yet completed the readiness audit.
The renderer makes missing config visible rather than silent so the
operations team has explicit evidence of what's outstanding before
flipping ``patient_pdf_workflow_recs_enabled`` for that lab.

Manufacturer-level config (DPO email, CDSCO license number, software
version) is held in Django settings rather than per-lab — see
``clinomic/settings.py`` ``AROGYABIOX_*`` and ``SOFTWARE_VERSION``.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0013_lab_patient_pdf_workflow_recs'),
    ]

    operations = [
        migrations.AddField(
            model_name='lab',
            name='grievance_email',
            field=models.EmailField(blank=True, default='', max_length=254),
        ),
        migrations.AddField(
            model_name='lab',
            name='privacy_notice_url',
            field=models.URLField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='lab',
            name='pathologist_name',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='lab',
            name='pathologist_registration',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='lab',
            name='pathologist_qualification',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='lab',
            name='pathologist_designation',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]

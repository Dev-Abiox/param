"""Patient PDF Disclosure Spec — Option A.

Adds ``Lab.patient_pdf_workflow_recs_enabled`` (default False).  When
False, the rule-based Workflow Recommendations section is suppressed
from patient-facing PDFs for that lab.  The on-screen ResultPanel
cards (clinician-facing) are unaffected.

Default of False applies to every existing row at migration time —
which is the intended Option A behaviour: every lab sees suppressed
patient PDFs until counsel sign-off, DPO appointment, and per-lab
signature workflow audit are all complete (Option B gate).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0012_encrypt_cbc_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='lab',
            name='patient_pdf_workflow_recs_enabled',
            field=models.BooleanField(
                default=False,
                help_text=(
                    "If True, render the rule-based Workflow Recommendations "
                    "section on patient-facing PDFs for screenings performed "
                    "at this lab.  Default False until counsel sign-off and "
                    "lab signature workflow are both in place."
                ),
            ),
        ),
    ]

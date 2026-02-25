"""
Change Patient unique_together from ['patient_id'] to ['patient_id', 'lab']
so different labs within the same tenant can have patients with the same
external patient ID.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0007_doctor_fk_protect'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='patient',
            unique_together={('patient_id', 'lab')},
        ),
    ]

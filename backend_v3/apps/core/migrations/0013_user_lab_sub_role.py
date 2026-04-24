"""P1-19 — add User.lab_sub_role for purpose-limited access within a Lab tenant.

New field defaults to empty string (UNSCOPED) so existing LAB users keep
full access until a Lab admin assigns them a sub-role.  No data migration
is required.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0012_user_email_unique'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='lab_sub_role',
            field=models.CharField(
                blank=True, default='',
                max_length=20,
                choices=[
                    ('',             '(unscoped — legacy full-access LAB user)'),
                    ('receptionist', 'Lab Receptionist'),
                    ('technician',   'Lab Technician'),
                    ('pathologist',  'Lab Pathologist'),
                    ('lab_admin',    'Lab Administrator'),
                ],
            ),
        ),
    ]

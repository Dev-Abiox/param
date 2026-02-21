from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_organization_onboarding_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('SUPER_ADMIN', 'Platform Administrator'),
                    ('ADMIN', 'Administrator'),
                    ('LAB', 'Lab Technician'),
                    ('DOCTOR', 'Doctor'),
                ],
                default='LAB',
                max_length=20,
            ),
        ),
    ]

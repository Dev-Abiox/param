"""Add mfa_method field to MFASettings (default TOTP for existing users)."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_remove_admin_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='mfasettings',
            name='mfa_method',
            field=models.CharField(
                choices=[('TOTP', 'Authenticator App'), ('EMAIL', 'Email Code')],
                default='TOTP',
                max_length=10,
            ),
        ),
    ]

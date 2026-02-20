from django.db import migrations, models
import apps.core.models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_rename_notification_index'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='onboarding_status',
            field=models.JSONField(default=apps.core.models._default_onboarding_status),
        ),
    ]

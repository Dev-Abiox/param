from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_notification'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mfasettings',
            name='secret_key',
            field=models.TextField(blank=True),
        ),
    ]

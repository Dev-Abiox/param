from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0010_p3_model_fixes'),
    ]

    operations = [
        migrations.AddField(
            model_name='screening',
            name='review_outcome',
            field=models.CharField(
                blank=True,
                choices=[('approved', 'Approved'), ('flagged', 'Flagged')],
                max_length=20,
                null=True,
            ),
        ),
    ]

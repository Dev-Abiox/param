"""Add db_index to razorpay_sub_id for faster webhook lookups."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tenantsubscription',
            name='razorpay_sub_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=100),
        ),
    ]

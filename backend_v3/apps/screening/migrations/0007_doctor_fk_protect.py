"""
Change Screening.doctor FK from SET_NULL to PROTECT to prevent
orphaned screenings when a doctor is accidentally deleted.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('screening', '0006_add_narrative_field'),
    ]

    operations = [
        migrations.AlterField(
            model_name='screening',
            name='doctor',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='screenings',
                to='screening.doctor',
            ),
        ),
    ]

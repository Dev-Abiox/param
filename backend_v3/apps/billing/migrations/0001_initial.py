"""
Initial billing migration: creates SubscriptionPlan, TenantSubscription,
UsageRecord, and PaymentEvent tables, then seeds the three product tiers.
"""

import uuid
import django.db.models.deletion
from django.db import migrations, models


def seed_plans(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    plans = [
        {
            'name': 'starter',
            'display_name': 'Starter',
            'monthly_limit': 500,
            'price_monthly': '2999.00',
            'razorpay_plan_id': '',
            'is_active': True,
        },
        {
            'name': 'professional',
            'display_name': 'Professional',
            'monthly_limit': 2000,
            'price_monthly': '7999.00',
            'razorpay_plan_id': '',
            'is_active': True,
        },
        {
            'name': 'enterprise',
            'display_name': 'Enterprise',
            'monthly_limit': -1,
            'price_monthly': '0.00',
            'razorpay_plan_id': '',
            'is_active': True,
        },
    ]
    for p in plans:
        SubscriptionPlan.objects.get_or_create(name=p['name'], defaults=p)


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SubscriptionPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
                ('display_name', models.CharField(max_length=100)),
                ('monthly_limit', models.IntegerField()),
                ('price_monthly', models.DecimalField(decimal_places=2, max_digits=10)),
                ('razorpay_plan_id', models.CharField(blank=True, max_length=100)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'billing_plans', 'ordering': ['price_monthly']},
        ),
        migrations.CreateModel(
            name='TenantSubscription',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(
                    choices=[
                        ('trial', 'Trial'), ('active', 'Active'), ('cancelled', 'Cancelled'),
                        ('past_due', 'Past Due'), ('expired', 'Expired'),
                    ],
                    default='trial',
                    max_length=20,
                )),
                ('razorpay_sub_id', models.CharField(blank=True, max_length=100)),
                ('current_period_start', models.DateTimeField()),
                ('current_period_end', models.DateTimeField()),
                ('current_period_count', models.IntegerField(default=0)),
                ('trial_end', models.DateTimeField(blank=True, null=True)),
                ('cancelled_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='subscription',
                    to='core.organization',
                )),
                ('plan', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='subscriptions',
                    to='billing.subscriptionplan',
                )),
            ],
            options={'db_table': 'billing_subscriptions'},
        ),
        migrations.CreateModel(
            name='UsageRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('period_start', models.DateField()),
                ('period_end', models.DateField()),
                ('screening_count', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='usage_records',
                    to='core.organization',
                )),
            ],
            options={
                'db_table': 'billing_usage_records',
                'ordering': ['-period_start'],
            },
        ),
        migrations.AddConstraint(
            model_name='usagerecord',
            constraint=models.UniqueConstraint(
                fields=['organization', 'period_start'],
                name='unique_org_period',
            ),
        ),
        migrations.CreateModel(
            name='PaymentEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('razorpay_event_id', models.CharField(max_length=200, unique=True)),
                ('event_type', models.CharField(max_length=100)),
                ('payload', models.JSONField()),
                ('processed', models.BooleanField(default=False)),
                ('error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('organization', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='payment_events',
                    to='core.organization',
                )),
            ],
            options={'db_table': 'billing_payment_events', 'ordering': ['-created_at']},
        ),
        migrations.RunPython(seed_plans, migrations.RunPython.noop),
    ]

"""
Data migration: set razorpay_plan_id for Starter and Professional plans.

These are Razorpay TEST-mode plan IDs created on 2026-02-23.
Production plan IDs should be set separately via Django admin or a migration.
"""

from django.db import migrations


def set_razorpay_plan_ids(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')

    SubscriptionPlan.objects.filter(name='starter').update(
        razorpay_plan_id='plan_SJY8pfd6y3BUnX',
    )
    SubscriptionPlan.objects.filter(name='professional').update(
        razorpay_plan_id='plan_SJY9erA6p5Mcjs',
    )


def clear_razorpay_plan_ids(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    SubscriptionPlan.objects.filter(
        name__in=['starter', 'professional'],
    ).update(razorpay_plan_id='')


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0004_webhook_endpoint'),
    ]

    operations = [
        migrations.RunPython(set_razorpay_plan_ids, clear_razorpay_plan_ids),
    ]

"""
Data migration: update SubscriptionPlan pricing and limits for the live
pricing rollout (April 2026).

Changes:
  - Starter:      ₹2999/500 analyses  → ₹7999/200 analyses
  - Professional: ₹7999/2000 analyses → RENAMED to "growth" (₹17999/500)
  - Chain:        NEW TIER            ₹27999/1000 analyses
  - Enterprise:   unchanged (custom pricing, contact sales)

The existing razorpay_plan_id values reference TEST mode plan IDs which
are invalid in LIVE mode.  They are cleared here — migration 0007 will
set the new live plan IDs once they are created in the Razorpay dashboard.

IMPORTANT: Any TenantSubscription rows currently linked to the
"professional" plan will automatically follow the rename because the FK
targets the plan row's id (not its name).  Verify no real customers are
on the old prices before running in production.
"""

from django.db import migrations


def update_plans_for_live(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')

    # Tier 1: Starter — ₹7999/mo, 200 analyses
    SubscriptionPlan.objects.filter(name='starter').update(
        display_name='Starter',
        price_monthly='7999.00',
        monthly_limit=200,
        razorpay_plan_id='',  # cleared — test plan ID invalid in live mode
    )

    # Tier 2: Growth (renamed from "professional") — ₹17999/mo, 500 analyses
    SubscriptionPlan.objects.filter(name='professional').update(
        name='growth',
        display_name='Growth',
        price_monthly='17999.00',
        monthly_limit=500,
        razorpay_plan_id='',
    )

    # Tier 3: Chain — NEW TIER — ₹27999/mo, 1000 analyses
    SubscriptionPlan.objects.update_or_create(
        name='chain',
        defaults={
            'display_name': 'Chain',
            'price_monthly': '27999.00',
            'monthly_limit': 1000,
            'razorpay_plan_id': '',
            'is_active': True,
        },
    )

    # Tier 4: Enterprise — unchanged (custom pricing, no Razorpay plan)
    SubscriptionPlan.objects.filter(name='enterprise').update(
        display_name='Enterprise',
        price_monthly='0.00',
        monthly_limit=-1,
        razorpay_plan_id='',
        is_active=True,
    )


def reverse_update(apps, schema_editor):
    """Revert to pre-April-2026 pricing and remove Chain tier."""
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')

    SubscriptionPlan.objects.filter(name='chain').delete()

    SubscriptionPlan.objects.filter(name='growth').update(
        name='professional',
        display_name='Professional',
        price_monthly='7999.00',
        monthly_limit=2000,
    )

    SubscriptionPlan.objects.filter(name='starter').update(
        display_name='Starter',
        price_monthly='2999.00',
        monthly_limit=500,
    )


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0005_set_razorpay_plan_ids'),
    ]
    operations = [
        migrations.RunPython(update_plans_for_live, reverse_update),
    ]

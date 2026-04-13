"""
Data migration: set LIVE-mode razorpay_plan_id values.

RUN THIS ONLY AFTER creating the plans in the Razorpay live dashboard:
  1. Log in to dashboard.razorpay.com (live mode)
  2. Subscriptions → Plans → Create new plan for each tier:
       - Starter — Amount: 799900 paise (₹7999), Frequency: Monthly
       - Growth  — Amount: 1799900 paise (₹17999), Frequency: Monthly
       - Chain   — Amount: 2799900 paise (₹27999), Frequency: Monthly
  3. Copy each plan_id (format: plan_XXXXXXXXXXXXXX)
  4. Fill in the STARTER_LIVE_ID / GROWTH_LIVE_ID / CHAIN_LIVE_ID below
  5. Run: python manage.py migrate billing 0007

If you have not yet created the live plans, the migration is a no-op
(because all IDs are empty strings).  Fill them in later and re-run
with `python manage.py migrate billing 0006 && python manage.py migrate billing 0007`
to re-apply.
"""

from django.db import migrations


# Live plan IDs from Razorpay dashboard (created 2026-04-13)
STARTER_LIVE_ID = 'plan_ScwbbW9OPk67yP'   # ₹7,999/mo, 200 analyses
GROWTH_LIVE_ID = 'plan_ScwcPiAzVQgIzF'    # ₹17,999/mo, 500 analyses
CHAIN_LIVE_ID = 'plan_Scwcnke31aFCTm'     # ₹27,999/mo, 1000 analyses
# (NB: the ₹27,999 plan is labelled "Professional" in the Razorpay
# dashboard but maps to our "chain" tier by price — rename in dashboard
# for clarity if desired; plan_id is the source of truth.)


def set_live_plan_ids(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')

    if STARTER_LIVE_ID:
        SubscriptionPlan.objects.filter(name='starter').update(razorpay_plan_id=STARTER_LIVE_ID)
    if GROWTH_LIVE_ID:
        SubscriptionPlan.objects.filter(name='growth').update(razorpay_plan_id=GROWTH_LIVE_ID)
    if CHAIN_LIVE_ID:
        SubscriptionPlan.objects.filter(name='chain').update(razorpay_plan_id=CHAIN_LIVE_ID)


def clear_plan_ids(apps, schema_editor):
    SubscriptionPlan = apps.get_model('billing', 'SubscriptionPlan')
    SubscriptionPlan.objects.filter(
        name__in=['starter', 'growth', 'chain'],
    ).update(razorpay_plan_id='')


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0006_update_plans_for_live_pricing'),
    ]
    operations = [
        migrations.RunPython(set_live_plan_ids, clear_plan_ids),
    ]

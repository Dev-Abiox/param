"""
Celery tasks for the billing app.

increment_usage          — atomically increments current_period_count for the
                           organisation that just ran a screening.  Fired as a
                           fire-and-forget task from PredictView so it does not
                           add latency to the prediction response path.

compute_monthly_rollups  — runs on the 1st of each month.  Archives the
                           previous month's usage into UsageRecord rows, then
                           resets all subscription counters to zero.
"""

import logging
from datetime import date, timedelta

import structlog
from celery import shared_task
from django.core.cache import cache

logger = structlog.get_logger(__name__)


@shared_task(
    name='billing.increment_usage',
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=60,
    acks_late=True,
)
def increment_usage(org_id: str, screening_id: str) -> None:
    """
    Atomically increment current_period_count for the given organisation.
    Uses F() expression to avoid race conditions when multiple workers fire
    this task concurrently.
    """
    if not org_id:
        return

    from django.db.models import F
    from apps.billing.models import TenantSubscription

    updated = TenantSubscription.objects.filter(organization_id=org_id).update(
        current_period_count=F('current_period_count') + 1
    )
    if updated:
        # Bust the plan-limit cache so PlanLimitMiddleware re-evaluates on the next request.
        cache.delete(f'plan_limit_over:{org_id}')
        logger.debug('billing.usage_incremented', org_id=org_id, screening_id=screening_id)
    else:
        logger.warning(
            'billing.no_subscription_found',
            org_id=org_id,
            screening_id=screening_id,
        )


@shared_task(
    name='billing.compute_monthly_rollups',
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=120,
    acks_late=True,
)
def compute_monthly_rollups() -> int:
    """
    Archive last month's usage and reset all subscription counters.
    Scheduled to run at 00:05 UTC on the 1st of each month.

    Returns the number of subscriptions updated.
    """
    from django.db import transaction
    from apps.billing.models import TenantSubscription, UsageRecord

    today = date.today()
    # Last day of the previous month
    last_month_end = today.replace(day=1) - timedelta(days=1)
    # First day of the previous month
    last_month_start = last_month_end.replace(day=1)
    # First day of next month (end of current period)
    first_of_next = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    current_period_end = first_of_next - timedelta(days=1)

    updated = 0
    sub_ids = list(
        TenantSubscription.objects.values_list('id', flat=True)
    )
    for sub_id in sub_ids:
        try:
            with transaction.atomic():
                sub = (
                    TenantSubscription.objects
                    .select_for_update()
                    .select_related('organization')
                    .get(id=sub_id)
                )
                UsageRecord.objects.update_or_create(
                    organization=sub.organization,
                    period_start=last_month_start,
                    defaults={
                        'period_end': last_month_end,
                        'screening_count': sub.current_period_count,
                    },
                )
                sub.current_period_count = 0
                sub.current_period_start = today
                sub.current_period_end = current_period_end
                sub.save(update_fields=[
                    'current_period_count',
                    'current_period_start',
                    'current_period_end',
                    'updated_at',
                ])
            cache.delete(f'plan_limit_over:{sub.organization_id}')
            updated += 1
        except Exception as exc:
            logger.error(
                'billing.rollup_failed',
                sub_id=str(sub_id),
                error=str(exc),
            )

    logger.info('billing.monthly_rollup_complete', subscriptions_updated=updated)
    return updated

"""
Celery tasks for the billing app.

increment_usage          — atomically increments current_period_count for the
                           organisation that just ran a screening.  Fired as a
                           fire-and-forget task from PredictView so it does not
                           add latency to the prediction response path.

compute_monthly_rollups  — runs on the 1st of each month.  Archives the
                           previous month's usage into UsageRecord rows, then
                           resets all subscription counters to zero.

send_usage_alert         — emails the org admin when usage crosses 80%, 90%, or
                           100% of their monthly limit.  Called from within
                           increment_usage after each successful increment.

send_welcome_email       — sends a welcome email to a newly signed-up admin.
                           Fired as a fire-and-forget task from SignupView.

send_high_risk_alert     — emails the referring doctor when a screening result
                           is classified as DEFICIENT (risk_class == 3).

deliver_webhook          — POSTs a signed JSON payload to a tenant webhook
                           endpoint.  Retries up to 3 times with exponential
                           backoff on failure.

trigger_webhook          — helper (not a Celery task) that looks up all active
                           WebhookEndpoint rows for a given org + event name and
                           fires deliver_webhook.delay() for each one.
"""

import hashlib
import hmac
import logging
from datetime import date, timedelta

import structlog
from celery import shared_task
from django.core.cache import cache

logger = structlog.get_logger(__name__)


# ── Usage Increment ─────────────────────────────────────────────────────────────

@shared_task(
    name='billing.increment_usage',
    max_retries=3,
    default_retry_delay=5,
    acks_late=True,
)
def increment_usage(org_id: str, screening_id: str) -> None:
    """
    Atomically increment current_period_count for the given organisation.
    Uses F() expression to avoid race conditions when multiple workers fire
    this task concurrently.

    Idempotency: uses a cache lock keyed on screening_id to prevent
    Celery at-least-once delivery from double-counting.

    After incrementing, checks whether the new count has just crossed the
    80%, 90%, or 100% usage threshold and, if so, fires send_usage_alert.
    """
    if not org_id or not screening_id:
        return

    # Idempotency guard — prevent double-increment from Celery retries
    dedup_key = f'billing_increment:{screening_id}'
    if not cache.add(dedup_key, '1', timeout=3600):
        logger.debug('billing.usage_increment_deduplicated', screening_id=screening_id)
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

        # Threshold alert check — re-fetch after the F() update to get the actual new value.
        try:
            sub = (
                TenantSubscription.objects
                .select_related('plan', 'organization')
                .get(organization_id=org_id)
            )
            limit = sub.plan.monthly_limit
            if limit > 0:
                new_count = sub.current_period_count
                # Compute which thresholds were just crossed (i.e., the previous
                # count was below the threshold and the new count is at or above it).
                for threshold_pct in (80, 90, 100):
                    threshold_count = int(limit * threshold_pct / 100)
                    prev_count = new_count - 1
                    if prev_count < threshold_count <= new_count:
                        send_usage_alert.delay(
                            org_id=org_id,
                            current_count=new_count,
                            limit=limit,
                            threshold_pct=threshold_pct,
                        )
                        logger.info(
                            'billing.usage_threshold_crossed',
                            org_id=org_id,
                            threshold_pct=threshold_pct,
                            count=new_count,
                            limit=limit,
                        )
        except TenantSubscription.DoesNotExist:
            pass
        except Exception as exc:
            logger.error(
                'billing.usage_threshold_check_failed',
                org_id=org_id,
                error=str(exc),
            )
    else:
        logger.warning(
            'billing.no_subscription_found',
            org_id=org_id,
            screening_id=screening_id,
        )


# ── Monthly Rollups ─────────────────────────────────────────────────────────────

@shared_task(
    name='billing.compute_monthly_rollups',
    max_retries=2,
    default_retry_delay=60,
)
def compute_monthly_rollups() -> int:
    """
    Archive last month's usage and reset all subscription counters.
    Scheduled to run at 00:05 UTC on the 1st of each month.

    Returns the number of subscriptions updated.
    """
    from django.db import transaction
    from apps.billing.models import TenantSubscription, UsageRecord

    # Distributed lock — prevent duplicate execution on rolling deploys
    lock_key = f'billing_rollup_lock:{date.today().isoformat()}'
    if not cache.add(lock_key, '1', timeout=3600):
        logger.info('billing.monthly_rollup_skipped_lock_held')
        return 0

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


# ── Email Notifications ─────────────────────────────────────────────────────────

@shared_task(
    name='billing.send_usage_alert',
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def send_usage_alert(org_id: str, current_count: int, limit: int, threshold_pct: int) -> None:
    """
    Send an email alert to the organisation admin when usage hits 80%, 90%,
    or 100% of their monthly screening limit.

    A per-threshold, per-billing-period deduplication key is stored in the
    cache so that only one alert per threshold crossing is ever sent, even if
    the task is retried.
    """
    from django.conf import settings
    from django.core.mail import send_mail
    from apps.billing.models import TenantSubscription
    from apps.core.models import User, Role

    # Deduplication: one alert per org × threshold × billing period
    dedup_key = f'usage_alert:{org_id}:{threshold_pct}:{date.today().replace(day=1).isoformat()}'
    if not cache.add(dedup_key, '1', timeout=60 * 60 * 24 * 32):  # 32 days TTL
        logger.debug(
            'billing.usage_alert_already_sent',
            org_id=org_id,
            threshold_pct=threshold_pct,
        )
        return

    # Find the LAB owner for this organisation
    lab_user = (
        User.objects
        .filter(organization_id=org_id, role=Role.LAB, is_active=True)
        .order_by('created_at')
        .first()
    )
    if not lab_user or not lab_user.email:
        logger.warning('billing.usage_alert_no_lab_email', org_id=org_id)
        return

    try:
        sub = TenantSubscription.objects.select_related('organization', 'plan').get(
            organization_id=org_id
        )
    except TenantSubscription.DoesNotExist:
        logger.warning('billing.usage_alert_no_subscription', org_id=org_id)
        return

    org_name = sub.organization.name
    plan_name = sub.plan.display_name

    if threshold_pct == 100:
        subject = f'[Clinomic] Usage limit reached — {org_name}'
        urgency_line = (
            'Your organisation has reached its monthly screening limit. '
            'New screenings will be blocked until the next billing cycle or you upgrade your plan.'
        )
    elif threshold_pct == 90:
        subject = f'[Clinomic] 90% of monthly usage reached — {org_name}'
        urgency_line = (
            'Your organisation has used 90% of its monthly screening allocation. '
            'Consider upgrading your plan to avoid disruption.'
        )
    else:  # 80%
        subject = f'[Clinomic] 80% of monthly usage reached — {org_name}'
        urgency_line = (
            'Your organisation has used 80% of its monthly screening allocation.'
        )

    message = (
        f'Hello,\n\n'
        f'{urgency_line}\n\n'
        f'Organisation : {org_name}\n'
        f'Plan         : {plan_name}\n'
        f'Usage        : {current_count} / {limit} screenings ({threshold_pct}%)\n\n'
        f'To upgrade your plan, log in to the Clinomic dashboard and visit\n'
        f'{settings.FRONTEND_URL}/billing\n\n'
        f'— The Clinomic Team'
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[lab_user.email],
            fail_silently=False,
        )
        logger.info(
            'billing.usage_alert_sent',
            org_id=org_id,
            threshold_pct=threshold_pct,
            recipient=lab_user.email,
        )
    except Exception as exc:
        # Clear the dedup key so a retry can attempt delivery again
        cache.delete(dedup_key)
        logger.error(
            'billing.usage_alert_send_failed',
            org_id=org_id,
            threshold_pct=threshold_pct,
            error=str(exc),
        )
        raise


@shared_task(
    name='billing.send_welcome_email',
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def send_welcome_email(user_id: str, org_name: str, plan_name: str, trial_end_iso: str) -> None:
    """
    Send a welcome email to the newly signed-up admin user.

    Parameters
    ----------
    user_id       : str  — UUID of the User record (public schema).
    org_name      : str  — Human-readable organisation name.
    plan_name     : str  — Display name of the chosen plan.
    trial_end_iso : str  — ISO-8601 datetime string for when the trial ends.
    """
    from django.conf import settings
    from django.core.mail import send_mail
    from apps.core.models import User

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning('billing.welcome_email_user_not_found', user_id=user_id)
        return

    if not user.email:
        logger.warning('billing.welcome_email_no_email', user_id=user_id)
        return

    subject = f'Welcome to Clinomic — {org_name}'
    message = (
        f'Hi {user.name or user.username},\n\n'
        f'Welcome to Clinomic! Your organisation "{org_name}" has been set up successfully.\n\n'
        f'Plan       : {plan_name}\n'
        f'Trial ends : {trial_end_iso}\n\n'
        f'Get started by logging in to your dashboard:\n'
        f'{settings.FRONTEND_URL}/dashboard\n\n'
        f'During your trial you have full access to all features. '
        f'To continue after the trial, visit the billing section of your dashboard.\n\n'
        f'If you have any questions, reply to this email or contact support at '
        f'support@clinomiclabs.com\n\n'
        f'— The Clinomic Team'
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(
            'billing.welcome_email_sent',
            user_id=user_id,
            org_name=org_name,
            recipient=user.email,
        )
    except Exception as exc:
        logger.error(
            'billing.welcome_email_send_failed',
            user_id=user_id,
            org_name=org_name,
            error=str(exc),
        )
        raise


@shared_task(
    name='billing.send_credentials_email',
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def send_credentials_email(user_id: str, plain_password: str, org_name: str) -> None:
    """
    Send login credentials to a newly created user (admin-created or onboarding).

    Parameters
    ----------
    user_id        : str — UUID of the User record (public schema).
    plain_password : str — The plain-text password assigned during creation.
    org_name       : str — Human-readable organisation name.
    """
    from django.conf import settings
    from django.core.mail import send_mail
    from apps.core.models import User

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning('billing.credentials_email_user_not_found', user_id=user_id)
        return

    if not user.email:
        logger.warning('billing.credentials_email_no_email', user_id=user_id)
        return

    login_url = f'{settings.FRONTEND_URL}/login'
    subject = f'Your Clinomic Account — {org_name}'
    message = (
        f'Hi {user.name or user.username},\n\n'
        f'An account has been created for you on the Clinomic platform '
        f'for organisation "{org_name}".\n\n'
        f'Here are your login credentials:\n'
        f'  Username : {user.username}\n'
        f'  Password : {plain_password}\n\n'
        f'Please sign in at: {login_url}\n\n'
        f'For security, we recommend changing your password after your first login.\n\n'
        f'If you have any questions, contact your administrator or reach out to '
        f'support@clinomiclabs.com\n\n'
        f'— The Clinomic Team'
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(
            'billing.credentials_email_sent',
            user_id=user_id,
            org_name=org_name,
            recipient=user.email,
        )
    except Exception as exc:
        logger.error(
            'billing.credentials_email_send_failed',
            user_id=user_id,
            org_name=org_name,
            error=str(exc),
        )
        raise


@shared_task(
    name='billing.send_mfa_otp_email',
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def send_mfa_otp_email(user_id: str, otp_code: str, recipient_email: str) -> None:
    """
    Send a 6-digit MFA verification code to the user's email.

    Parameters
    ----------
    user_id         : str — UUID of the User record.
    otp_code        : str — The 6-digit OTP code.
    recipient_email : str — Email address to send the code to.
    """
    from django.conf import settings as django_settings
    from django.core.mail import send_mail

    subject = 'Your Clinomic verification code'
    message = (
        f'Your Clinomic verification code is:\n\n'
        f'    {otp_code}\n\n'
        f'This code expires in 5 minutes. If you did not request this code, '
        f'please ignore this email.\n\n'
        f'— The Clinomic Team'
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient_email],
            fail_silently=False,
        )
        logger.info(
            'billing.mfa_otp_email_sent',
            user_id=user_id,
            recipient=recipient_email,
        )
    except Exception as exc:
        logger.error(
            'billing.mfa_otp_email_send_failed',
            user_id=user_id,
            recipient=recipient_email,
            error=str(exc),
        )
        raise


@shared_task(
    name='billing.send_high_risk_alert',
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def send_high_risk_alert(
    screening_id: str,
    org_id: str,
    doctor_id: str | None = None,
) -> None:
    """
    Email the referring doctor when a screening is classified as DEFICIENT
    (risk_class == 3).

    The task runs inside the tenant's schema so it can resolve the Screening
    and Doctor records.  org_id is used to set the correct schema context via
    django_tenants.

    Parameters
    ----------
    screening_id : str       — UUID of the Screening record.
    org_id       : str       — UUID of the tenant Organisation.
    doctor_id    : str|None  — UUID of the Doctor record (optional; the task
                               will fall back to the doctor on the Screening).
    """
    from django.conf import settings
    from django.core.mail import send_mail
    from django_tenants.utils import schema_context
    from apps.core.models import Organization

    try:
        org = Organization.objects.get(id=org_id)
    except Organization.DoesNotExist:
        logger.warning('billing.high_risk_alert_org_not_found', org_id=org_id)
        return

    with schema_context(org.schema_name):
        from apps.screening.models import Screening, RiskClass

        try:
            screening = (
                Screening.objects
                .select_related('doctor', 'patient')
                .get(id=screening_id)
            )
        except Screening.DoesNotExist:
            logger.warning(
                'billing.high_risk_alert_screening_not_found',
                screening_id=screening_id,
            )
            return

        # Confirm still DEFICIENT (idempotency safety)
        if screening.risk_class != RiskClass.DEFICIENT:
            return

        doctor = screening.doctor
        if not doctor or not doctor.email:
            logger.info(
                'billing.high_risk_alert_no_doctor_email',
                screening_id=screening_id,
            )
            return

        subject = f'[Clinomic] High-Risk B12 Screening Alert — Patient {screening.patient.patient_id}'
        message = (
            f'Dear Dr. {doctor.name},\n\n'
            f'A B12 screening result for one of your patients has been classified as '
            f'DEFICIENT and requires your attention.\n\n'
            f'Screening ID : {screening_id}\n'
            f'Patient ID   : {screening.patient.patient_id}\n'
            f'Risk Class   : {screening.get_risk_class_display()}\n'
            f'Result       : {screening.label_text}\n'
            f'Performed by : {screening.performed_by}\n\n'
            f'Recommendation:\n'
            f'Serum B12 measurement recommended. Clinical correlation advised.\n\n'
            f'View the full report in your Clinomic dashboard:\n'
            f'{settings.FRONTEND_URL}/screenings/{screening_id}\n\n'
            f'— The Clinomic Platform'
        )

        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[doctor.email],
                fail_silently=False,
            )
            logger.info(
                'billing.high_risk_alert_sent',
                screening_id=screening_id,
                doctor_id=str(doctor.id),
                recipient=doctor.email,
            )
        except Exception as exc:
            logger.error(
                'billing.high_risk_alert_send_failed',
                screening_id=screening_id,
                error=str(exc),
            )
            raise


# ── Webhook Delivery ────────────────────────────────────────────────────────────

@shared_task(
    name='billing.deliver_webhook',
    bind=True,
    max_retries=3,
    acks_late=True,
)
def deliver_webhook(
    self,
    webhook_endpoint_id: str,
    event_name: str,
    payload: dict,
) -> None:
    """
    POST a signed JSON payload to a tenant webhook endpoint.

    Signing
    -------
    The raw JSON body is signed with HMAC-SHA256 using the endpoint's secret.
    The signature is sent in the ``X-Clinomic-Signature`` header as::

        sha256=<hex-digest>

    Retry strategy
    --------------
    Up to 3 retries with exponential back-off (60 s, 120 s, 240 s).

    Parameters
    ----------
    webhook_endpoint_id : str   — UUID of the WebhookEndpoint row.
    event_name          : str   — e.g. "screening.completed"
    payload             : dict  — Arbitrary JSON-serialisable event data.
    """
    import json
    import requests
    from django.utils import timezone
    from apps.billing.models import WebhookEndpoint

    try:
        endpoint = WebhookEndpoint.objects.get(id=webhook_endpoint_id, is_active=True)
    except WebhookEndpoint.DoesNotExist:
        logger.warning(
            'billing.deliver_webhook_endpoint_not_found',
            endpoint_id=webhook_endpoint_id,
        )
        return

    body = json.dumps({
        'event': event_name,
        'timestamp': timezone.now().isoformat(),
        'data': payload,
    }, default=str)

    # Sign with HMAC-SHA256
    signature = hmac.new(
        endpoint.secret.encode('utf-8'),
        body.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()

    headers = {
        'Content-Type': 'application/json',
        'X-Clinomic-Signature': f'sha256={signature}',
        'X-Clinomic-Event': event_name,
    }

    attempt = self.request.retries + 1
    logger.info(
        'billing.webhook_delivery_attempt',
        endpoint_id=webhook_endpoint_id,
        url=endpoint.url,
        event=event_name,
        attempt=attempt,
    )

    try:
        response = requests.post(
            endpoint.url,
            data=body,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        logger.info(
            'billing.webhook_delivered',
            endpoint_id=webhook_endpoint_id,
            url=endpoint.url,
            event=event_name,
            status_code=response.status_code,
        )
    except requests.RequestException as exc:
        logger.warning(
            'billing.webhook_delivery_failed',
            endpoint_id=webhook_endpoint_id,
            url=endpoint.url,
            event=event_name,
            attempt=attempt,
            error=str(exc),
        )
        # Exponential backoff: 60 s, 120 s, 240 s
        countdown = 60 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)


def trigger_webhook(organization, event_name: str, payload: dict) -> None:
    """
    Find all active WebhookEndpoint rows for *organization* that are
    subscribed to *event_name* and fire ``deliver_webhook.delay()`` for each.

    This is a regular function (not a Celery task) intended to be called from
    views or other tasks.  It delegates actual HTTP delivery to
    ``deliver_webhook`` so the caller is never blocked.

    Parameters
    ----------
    organization : Organization  — The tenant Organisation instance.
    event_name   : str           — e.g. "screening.completed"
    payload      : dict          — Arbitrary JSON-serialisable event data.
    """
    from apps.billing.models import WebhookEndpoint

    endpoints = WebhookEndpoint.objects.filter(
        organization=organization,
        is_active=True,
    )

    fired = 0
    for endpoint in endpoints:
        # The events field is a list like ["screening.completed", "consent.revoked"]
        if event_name in (endpoint.events or []):
            deliver_webhook.delay(
                webhook_endpoint_id=str(endpoint.id),
                event_name=event_name,
                payload=payload,
            )
            fired += 1

    if fired:
        logger.info(
            'billing.webhooks_triggered',
            org_id=str(organization.id),
            event_name=event_name,
            count=fired,
        )


@shared_task(
    name='billing.send_lab_created_email',
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def send_lab_created_email(
    self,
    user_id: str,
    org_name: str,
    plan_name: str,
    temp_password: str,
) -> None:
    """
    Email the admin user when a super admin creates a new lab on their behalf.
    Contains temporary credentials and login instructions.
    """
    from django.conf import settings
    from django.core.mail import send_mail
    from apps.core.models import User

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        logger.warning('billing.lab_created_email_user_not_found', user_id=user_id)
        return

    if not user.email:
        logger.warning('billing.lab_created_email_no_email', user_id=user_id)
        return

    subject = f'Your Clinomic account is ready — {org_name}'
    message = (
        f'Hi {user.name or user.username},\n\n'
        f'Your organisation "{org_name}" has been set up on Clinomic.\n\n'
        f'Plan        : {plan_name}\n'
        f'Login URL   : {settings.FRONTEND_URL}/login\n'
        f'Username    : {user.username}\n'
        f'Password    : {temp_password}\n\n'
        f'IMPORTANT: Please change your password immediately after logging in.\n'
        f'You will also be required to set up two-factor authentication (MFA)\n'
        f'before accessing sensitive features.\n\n'
        f'Steps to get started:\n'
        f'  1. Log in at {settings.FRONTEND_URL}/login\n'
        f'  2. Change your password in Settings\n'
        f'  3. Set up MFA via the Security section\n'
        f'  4. Complete the onboarding wizard\n\n'
        f'If you have questions, contact support@clinomiclabs.com\n\n'
        f'— The Clinomic Team'
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(
            'billing.lab_created_email_sent',
            user_id=user_id,
            org_name=org_name,
            recipient=user.email,
        )
    except Exception as exc:
        logger.error(
            'billing.lab_created_email_failed',
            user_id=user_id,
            org_name=org_name,
            error=str(exc),
        )
        raise self.retry(exc=exc)

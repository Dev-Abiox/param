"""
Billing API views.

WebhookView             POST /api/billing/webhook/
OnboardingStatusView    PATCH /api/billing/onboarding/
AdminUsageView          GET  /api/billing/admin/usage
AdminBillingView        GET  /api/billing/admin/billing
AdminBillingUpgradeView POST /api/billing/admin/billing/upgrade
APIKeyListView          GET  /api/billing/admin/api-keys/
                        POST /api/billing/admin/api-keys/
APIKeyDetailView        DELETE /api/billing/admin/api-keys/<uuid:pk>/
WebhookListView         GET  /api/billing/admin/webhooks/
                        POST /api/billing/admin/webhooks/
WebhookDetailView       DELETE /api/billing/admin/webhooks/<uuid:pk>/
"""

import hashlib
import ipaddress
import secrets
import socket
from datetime import timedelta
from urllib.parse import urlparse

import structlog
from django.conf import settings
from django.db import DatabaseError, transaction
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core.models import Role
from apps.core.permissions import HasRole, IsMFAVerified
from apps.core.throttling import AdminEndpointThrottle

from .models import APIKey, PaymentEvent, SubscriptionPlan, TenantSubscription, UsageRecord, WebhookEndpoint, VALID_SCOPES
from .serializers import (
    OnboardingStatusSerializer,
    SubscriptionPlanSerializer,
    TenantSubscriptionSerializer,
    UsageRecordSerializer,
)

logger = structlog.get_logger(__name__)


# Monthly billing period used to advance current_period_end on
# `subscription.charged`. Named constant so the webhook handler and any
# future billing helpers can't drift from each other.
BILLING_PERIOD_DAYS = 30


# ── helpers ────────────────────────────────────────────────────────────────────

def _razorpay_client():
    """Return a Razorpay SDK client built from the configured credentials.

    Centralised so the three call sites (webhook signature verify, subscription
    create on upgrade, payment-verify subscription fetch) can't drift on which
    settings keys they read or how they construct the client.
    """
    import razorpay
    return razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )


def _validate_webhook_url(url: str) -> str | None:
    """Validate a webhook URL is HTTPS and not targeting private/internal networks.

    Returns an error message string if invalid, or None if the URL is safe.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return 'Invalid URL.'

    # Require HTTPS — webhook payloads contain sensitive event data
    if parsed.scheme != 'https':
        return 'Webhook URLs must use HTTPS.'

    hostname = parsed.hostname
    if not hostname:
        return 'Invalid URL: missing hostname.'

    # Resolve hostname to IP and block private/reserved ranges (SSRF protection)
    try:
        resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _type, _proto, _canonname, sockaddr in resolved:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return 'Webhook URLs must not target private or internal networks.'
    except (socket.gaierror, ValueError):
        return 'Could not resolve webhook URL hostname.'

    return None




# ── Onboarding Status ──────────────────────────────────────────────────────────

class OnboardingStatusView(APIView):
    """
    PATCH /api/billing/onboarding/
    Allows the frontend wizard to mark steps as completed.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.SUPER_ADMIN, Role.LAB]

    def get(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(org.onboarding_status)

    def patch(self, request):
        serializer = OnboardingStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        # Merge only the provided keys
        current = dict(org.onboarding_status or {})
        current.update(serializer.validated_data)
        org.onboarding_status = current
        org.save(update_fields=['onboarding_status', 'updated_at'])
        return Response(org.onboarding_status)


# ── Razorpay Webhook ───────────────────────────────────────────────────────────

class WebhookRateThrottle(AnonRateThrottle):
    rate = '60/min'


# Razorpay's documented webhook source IP ranges. HMAC-SHA256 is the primary
# defence — this list is defence-in-depth against DoS / forgery attempts.
# Override via settings.RAZORPAY_WEBHOOK_ALLOWED_CIDRS if Razorpay updates them.
# Set to empty string to disable the check (e.g. if Razorpay's published list is
# unavailable or you're behind a proxy that masks the source IP).
DEFAULT_RAZORPAY_CIDRS = (
    "52.66.143.197/32",
    "13.232.232.95/32",
    "13.234.131.187/32",
    "3.6.92.66/32",
    "13.235.157.91/32",
    "13.232.232.96/27",  # broader range used in some regions
)


def _client_ip(request) -> str:
    """Return the client IP, trusting X-Forwarded-For only when behind nginx."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        # First IP in the chain is the original client
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


def _is_razorpay_ip(ip_str: str) -> bool:
    """Check if *ip_str* falls within any of Razorpay's published IP ranges.

    Disabled (returns True) when:
      - APP_ENV env var is testing/dev/development
      - ``settings.RAZORPAY_WEBHOOK_ALLOWED_CIDRS`` is set to an empty value
    """
    # Read APP_ENV directly from os.environ, NOT settings — some tests patch
    # apps.billing.views.settings to a MagicMock which would otherwise turn
    # `settings.APP_ENV` into a MagicMock and bypass this guard.
    import os
    if os.environ.get('APP_ENV', 'dev').lower() in ('testing', 'test', 'dev', 'development'):
        return True

    if not ip_str:
        return False
    cidrs = getattr(settings, 'RAZORPAY_WEBHOOK_ALLOWED_CIDRS', None)
    if cidrs is None:
        cidrs = DEFAULT_RAZORPAY_CIDRS
    if not cidrs:
        return True  # check explicitly disabled
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    for cidr in cidrs:
        try:
            if ip in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


# All handlers take a uniform (sub, sub_entity, now) signature so the
# dispatch table can call them without special-casing. Unused positional
# args are prefixed `_` to document "intentionally ignored".

def _handle_subscription_activated(sub, sub_entity, _now):
    sub.transition_to(TenantSubscription.Status.ACTIVE)
    rz_plan_id = sub_entity.get('plan_id', '')
    if rz_plan_id:
        new_plan = SubscriptionPlan.objects.filter(
            razorpay_plan_id=rz_plan_id, is_active=True
        ).first()
        if new_plan and new_plan.pk != sub.plan_id:
            sub.plan = new_plan
    sub.save(update_fields=['status', 'plan', 'updated_at'])


def _handle_subscription_charged(sub, _sub_entity, now):
    sub.current_period_count = 0
    sub.current_period_start = now
    sub.current_period_end = now + timedelta(days=BILLING_PERIOD_DAYS)
    sub.save(update_fields=[
        'current_period_count',
        'current_period_start',
        'current_period_end',
        'updated_at',
    ])


def _handle_subscription_cancelled(sub, _sub_entity, now):
    sub.transition_to(TenantSubscription.Status.CANCELLED)
    sub.cancelled_at = now
    sub.save(update_fields=['status', 'cancelled_at', 'updated_at'])


def _handle_payment_failed(sub, _sub_entity, _now):
    sub.transition_to(TenantSubscription.Status.PAST_DUE)
    sub.save(update_fields=['status', 'updated_at'])


# Event-type → handler. Any event not in this map is still recorded in
# PaymentEvent but triggers no state transition. This makes adding a
# new webhook event a one-line change.
_WEBHOOK_HANDLERS = {
    'subscription.activated': _handle_subscription_activated,
    'subscription.charged':   _handle_subscription_charged,
    'subscription.cancelled': _handle_subscription_cancelled,
    'payment.failed':         _handle_payment_failed,
}

# Events that must invalidate cached plan-limit decisions post-commit.
_CACHE_BUST_EVENTS = {'subscription.activated', 'subscription.charged'}


class WebhookView(APIView):
    """
    POST /api/billing/webhook/
    Receives Razorpay subscription webhook events, verifies the HMAC-SHA256
    signature, and updates TenantSubscription state accordingly.
    All raw events are stored in PaymentEvent for idempotency + audit.

    The body of post() is a flat pipeline:
        1. source-IP allowlist (defence in depth — HMAC is canonical)
        2. HMAC signature verification
        3. event-id idempotency check
        4. raw-event persistence
        5. locked state transition via _WEBHOOK_HANDLERS dispatch
        6. on_commit cache bust for plan-limit decisions
    """
    permission_classes = [AllowAny]
    throttle_classes = [WebhookRateThrottle]

    def _verify_source(self, request):
        """Return (ok, response_if_blocked)."""
        client_ip = _client_ip(request)
        if not _is_razorpay_ip(client_ip):
            logger.warning('billing.webhook_blocked_ip', ip=client_ip)
            return False, Response({'error': 'forbidden'}, status=status.HTTP_403_FORBIDDEN)
        return True, None

    def _verify_signature(self, request):
        """Return (ok, response_if_blocked). Reads the secret from settings."""
        sig = request.headers.get('X-Razorpay-Signature', '')
        webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')
        if not webhook_secret:
            logger.error('billing.webhook_secret_not_configured')
            return False, Response(
                {'error': 'webhook not configured'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            client = _razorpay_client()
            client.utility.verify_webhook_signature(
                request.body.decode('utf-8'), sig, webhook_secret
            )
        except Exception as exc:
            logger.warning('billing.webhook_invalid_signature', error=type(exc).__name__)
            return False, Response(
                {'error': 'invalid signature'}, status=status.HTTP_401_UNAUTHORIZED
            )
        return True, None

    def _apply_state_transition(self, sub, event_type, sub_entity, razorpay_sub_id, pe):
        """
        Take the row lock, run the handler for event_type, mark the
        PaymentEvent processed. Returns (ok, response_if_short_circuit).
        """
        now = timezone.now()
        try:
            with transaction.atomic():
                # Lock the subscription row to prevent concurrent webhook races.
                # nowait=True: if another worker is already processing a webhook
                # for the same subscription, fail fast instead of blocking the
                # request thread — we return 503 below so Razorpay retries.
                try:
                    sub = (
                        TenantSubscription.objects
                        .select_for_update(nowait=True)
                        .select_related('organization')
                        .get(pk=sub.pk)
                    )
                except DatabaseError:
                    logger.warning(
                        'billing.webhook_lock_contended',
                        event_type=event_type,
                        sub_id=razorpay_sub_id,
                    )
                    return False, Response(
                        {'status': 'retry'},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )

                handler = _WEBHOOK_HANDLERS.get(event_type)
                if handler is not None:
                    handler(sub, sub_entity, now)

                pe.processed = True
                pe.save(update_fields=['processed'])

            if event_type in _CACHE_BUST_EVENTS:
                org_id = sub.organization_id
                from django.db import transaction as db_tx
                from django.core.cache import cache
                db_tx.on_commit(lambda: cache.delete(f'plan_limit_over:{org_id}'))

            logger.info(
                'billing.webhook_processed',
                event_type=event_type,
                sub_id=razorpay_sub_id,
            )
            return True, None
        except Exception as exc:
            # Sanitize error — never store raw exception details (may contain DB paths, etc.)
            safe_error = f'{type(exc).__name__}: {event_type}'
            pe.error = safe_error
            pe.save(update_fields=['error'])
            logger.error('billing.webhook_error', event_type=event_type, error=str(exc))
            return False, None  # still return 200 to stop Razorpay retries

    def post(self, request):
        ok, err = self._verify_source(request)
        if not ok:
            return err

        ok, err = self._verify_signature(request)
        if not ok:
            return err

        data = request.data
        event_type = data.get('event', '')
        sub_entity = (
            data.get('payload', {})
            .get('subscription', {})
            .get('entity', {})
        )
        razorpay_sub_id = sub_entity.get('id', '')
        event_id = data.get('id')
        if not event_id:
            logger.warning('billing.webhook_missing_event_id', event_type=event_type)
            return Response({'error': 'missing event id'}, status=status.HTTP_400_BAD_REQUEST)

        if PaymentEvent.objects.filter(razorpay_event_id=event_id).exists():
            return Response({'status': 'already_processed'})

        sub = (
            TenantSubscription.objects
            .filter(razorpay_sub_id=razorpay_sub_id)
            .select_related('organization')
            .first()
        )

        pe = PaymentEvent.objects.create(
            organization=sub.organization if sub else None,
            razorpay_event_id=event_id,
            event_type=event_type,
            payload=data,
        )

        if sub:
            _, early = self._apply_state_transition(
                sub, event_type, sub_entity, razorpay_sub_id, pe
            )
            if early is not None:
                return early

        return Response({'status': 'ok'})


# ── Admin — Usage ──────────────────────────────────────────────────────────────

class AdminUsageView(APIView):
    """
    GET /api/billing/admin/usage
    Returns current usage stats and 6-month history for the admin's org.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    throttle_classes = [AdminEndpointThrottle]
    required_roles = [Role.SUPER_ADMIN, Role.LAB]

    def get(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        # Billing tables live in the public schema (SHARED_APPS), but
        # JWTTenantMiddleware may have switched to the tenant schema.
        with schema_context('public'):
            try:
                sub = TenantSubscription.objects.select_related('plan').get(organization=org)
            except TenantSubscription.DoesNotExist:
                return Response(
                    {'error': 'No active subscription found. Please contact support.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

            lim = sub.plan.monthly_limit
            pct = (
                round(sub.current_period_count / lim * 100, 1)
                if lim > 0 else 0
            )

            history = UsageRecord.objects.filter(organization=org).order_by('-period_start')[:6]

            return Response({
                'plan': sub.plan.display_name,
                'monthly_limit': lim,            # -1 = unlimited
                'current_count': sub.current_period_count,
                'period_start': sub.current_period_start,
                'period_end': sub.current_period_end,
                'pct_used': pct,
                'status': sub.status,
                'trial_end': sub.trial_end,
                'history': UsageRecordSerializer(history, many=True).data,
            })


# ── Admin — Billing ────────────────────────────────────────────────────────────

class AdminBillingView(APIView):
    """
    GET /api/billing/admin/billing
    Returns the current plan + all available plans for the upgrade picker.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    throttle_classes = [AdminEndpointThrottle]
    required_roles = [Role.SUPER_ADMIN, Role.LAB]

    def get(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        with schema_context('public'):
            try:
                sub = TenantSubscription.objects.select_related('plan').get(organization=org)
            except TenantSubscription.DoesNotExist:
                return Response(
                    {'error': 'No active subscription found. Please contact support.'},
                    status=status.HTTP_404_NOT_FOUND,
                )

            all_plans = SubscriptionPlan.objects.filter(is_active=True).order_by('price_monthly')

            return Response({
                'subscription': TenantSubscriptionSerializer(sub).data,
                'available_plans': SubscriptionPlanSerializer(all_plans, many=True).data,
            })


class AdminBillingUpgradeView(APIView):
    """
    POST /api/billing/admin/billing/upgrade
    Body: { "plan": "professional" }

    Creates a Razorpay subscription for the new plan and returns the
    subscription_id + key so the frontend can open Razorpay Checkout.

    The DB is NOT updated here — the plan change is only committed when
    the Razorpay `subscription.activated` webhook arrives.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    throttle_classes = [AdminEndpointThrottle]
    required_roles = [Role.SUPER_ADMIN, Role.LAB]

    def post(self, request):
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            return Response(
                {'error': 'Payment gateway is not configured. Please contact support.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        plan_name = (request.data.get('plan') or '').strip().lower()
        if not plan_name:
            return Response({'error': 'plan is required'}, status=status.HTTP_400_BAD_REQUEST)

        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        with schema_context('public'):
            try:
                new_plan = SubscriptionPlan.objects.get(name=plan_name, is_active=True)
            except SubscriptionPlan.DoesNotExist:
                return Response({'error': f'Unknown plan: {plan_name}'}, status=status.HTTP_400_BAD_REQUEST)

            if not new_plan.razorpay_plan_id:
                return Response(
                    {'error': f'Plan "{plan_name}" is not linked to a Razorpay plan.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                sub = TenantSubscription.objects.get(organization=org)
            except TenantSubscription.DoesNotExist:
                return Response({'error': 'No subscription found'}, status=status.HTTP_404_NOT_FOUND)

            if sub.plan.name == plan_name:
                return Response({'error': 'Already on this plan.'}, status=status.HTTP_400_BAD_REQUEST)

            # Create a Razorpay subscription for the new plan
            try:
                client = _razorpay_client()
                rz_sub = client.subscription.create({
                    'plan_id': new_plan.razorpay_plan_id,
                    'total_count': 12,  # 12 billing cycles
                    'notes': {
                        'org_id': str(org.id),
                        'org_name': org.name,
                        'old_plan': sub.plan.name,
                        'new_plan': plan_name,
                    },
                })
            except Exception as exc:
                logger.error('billing.razorpay_create_sub_failed', error=str(exc), org=org.name)
                return Response(
                    {'error': 'Failed to create payment subscription. Please try again.'},
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            # Store the Razorpay subscription ID so the webhook can match it
            sub.razorpay_sub_id = rz_sub['id']
            sub.save(update_fields=['razorpay_sub_id', 'updated_at'])

        logger.info(
            'billing.upgrade_initiated',
            org=org.name,
            old=sub.plan.name,
            new=plan_name,
            razorpay_sub_id=rz_sub['id'],
        )
        return Response({
            'subscription_id': rz_sub['id'],
            'razorpay_key_id': settings.RAZORPAY_KEY_ID,
            'plan': plan_name,
            'display_name': new_plan.display_name,
        })


class PaymentVerifyView(APIView):
    """
    POST /api/billing/admin/verify-payment/

    Verify a Razorpay subscription payment signature returned by the
    Razorpay Checkout client-side handler. The frontend MUST call this
    before showing a "success" UI — never trust the handler firing alone.

    Body:
        razorpay_payment_id      — required
        razorpay_subscription_id — required (subscription flow)
        razorpay_signature       — required

    Returns 200 with {verified: True} on success, 400 on bad input,
    422 on signature mismatch.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    throttle_classes = [AdminEndpointThrottle]
    required_roles = [Role.SUPER_ADMIN, Role.LAB]

    def post(self, request):
        if not settings.RAZORPAY_KEY_SECRET:
            return Response(
                {'error': 'Payment gateway not configured'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        payment_id = (request.data.get('razorpay_payment_id') or '').strip()
        sub_id = (request.data.get('razorpay_subscription_id') or '').strip()
        signature = (request.data.get('razorpay_signature') or '').strip()

        if not (payment_id and sub_id and signature):
            return Response(
                {'error': 'razorpay_payment_id, razorpay_subscription_id, and razorpay_signature are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify the signature matches HMAC-SHA256(payment_id|subscription_id, key_secret)
        import hmac as _hmac
        import hashlib as _hashlib
        msg = f'{payment_id}|{sub_id}'.encode()
        expected = _hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            msg,
            _hashlib.sha256,
        ).hexdigest()
        if not _hmac.compare_digest(expected, signature):
            logger.warning(
                'billing.payment_verify_signature_mismatch',
                payment_id=payment_id,
                sub_id=sub_id,
                user=request.user.username,
            )
            return Response(
                {'error': 'Invalid payment signature', 'verified': False},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # Optional: confirm the subscription exists in Razorpay (defence in depth).
        # Failures here are non-fatal — the signature itself is the canonical proof.
        try:
            client = _razorpay_client()
            client.subscription.fetch(sub_id)
        except Exception as exc:
            logger.warning(
                'billing.payment_verify_subscription_fetch_failed',
                sub_id=sub_id,
                error=type(exc).__name__,
            )

        # Surface the matching DB subscription so the frontend can refresh state.
        org = getattr(request.user, 'organization', None)
        with schema_context('public'):
            db_sub = TenantSubscription.objects.filter(razorpay_sub_id=sub_id).first()

        logger.info(
            'billing.payment_verified',
            user=request.user.username,
            org=getattr(org, 'name', None),
            payment_id=payment_id,
            sub_id=sub_id,
        )
        return Response({
            'verified': True,
            'razorpay_subscription_id': sub_id,
            'razorpay_payment_id': payment_id,
            'db_subscription_status': db_sub.status if db_sub else None,
        })


# ── Admin — API Key Management ─────────────────────────────────────────────────

class APIKeyListView(APIView):
    """
    GET  /api/billing/admin/api-keys/
        List all active (and inactive) API keys for the admin's organisation.
        Sensitive fields (key_hash) are never returned.

    POST /api/billing/admin/api-keys/
        Create a new API key.  The raw key value is returned **only once** in
        the response body — it cannot be recovered later.

        Expected body:
        {
            "name": "CI Pipeline",
            "scopes": ["screening:read", "analytics:read"],
            "rate_limit": 120          # optional, default 60
        }
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    throttle_classes = [AdminEndpointThrottle]
    required_roles = [Role.SUPER_ADMIN, Role.LAB]

    def get(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        keys = (
            APIKey.objects
            .filter(organization=org)
            .select_related('created_by')
            .order_by('-created_at')
        )

        data = [
            {
                'id': str(k.id),
                'name': k.name,
                'scopes': k.scopes,
                'rate_limit': k.rate_limit,
                'is_active': k.is_active,
                'created_by': k.created_by.username if k.created_by else None,
                'last_used_at': k.last_used_at,
                'created_at': k.created_at,
            }
            for k in keys
        ]
        return Response(data)

    def post(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'error': '"name" is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if len(name) > 100:
            return Response({'error': '"name" must be 100 characters or fewer.'}, status=status.HTTP_400_BAD_REQUEST)

        scopes = request.data.get('scopes', [])
        if not isinstance(scopes, list):
            return Response({'error': '"scopes" must be a list.'}, status=status.HTTP_400_BAD_REQUEST)
        invalid_scopes = [s for s in scopes if s not in VALID_SCOPES]
        if invalid_scopes:
            return Response(
                {
                    'error': f'Invalid scope(s): {invalid_scopes}. '
                             f'Valid scopes are: {sorted(VALID_SCOPES)}.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not scopes:
            return Response({'error': 'At least one scope is required.'}, status=status.HTTP_400_BAD_REQUEST)

        rate_limit = request.data.get('rate_limit', 60)
        try:
            rate_limit = int(rate_limit)
            if rate_limit < 1:
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {'error': '"rate_limit" must be a positive integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate a cryptographically secure key and store only its digest
        raw_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        api_key = APIKey.objects.create(
            organization=org,
            name=name,
            key_hash=key_hash,
            scopes=scopes,
            rate_limit=rate_limit,
            is_active=True,
            created_by=request.user,
        )

        logger.info(
            'api_key.created',
            org=org.name,
            key_id=str(api_key.id),
            name=name,
            scopes=scopes,
            created_by=request.user.username,
        )

        return Response(
            {
                'id': str(api_key.id),
                'name': api_key.name,
                'key': raw_key,          # shown ONCE — cannot be recovered
                'scopes': api_key.scopes,
                'rate_limit': api_key.rate_limit,
                'is_active': api_key.is_active,
                'created_at': api_key.created_at,
                'warning': (
                    'Store this key securely. It will not be shown again.'
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class APIKeyDetailView(APIView):
    """
    DELETE /api/billing/admin/api-keys/<uuid:pk>/
        Revoke (soft-delete) an API key by setting is_active=False.
        The key is not physically removed so audit logs remain intact.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    throttle_classes = [AdminEndpointThrottle]
    required_roles = [Role.SUPER_ADMIN, Role.LAB]

    def delete(self, request, pk):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            api_key = APIKey.objects.get(pk=pk, organization=org)
        except APIKey.DoesNotExist:
            return Response({'error': 'API key not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not api_key.is_active:
            return Response({'error': 'API key is already revoked.'}, status=status.HTTP_400_BAD_REQUEST)

        api_key.is_active = False
        api_key.save(update_fields=['is_active', 'updated_at'])

        logger.info(
            'api_key.revoked',
            org=org.name,
            key_id=str(api_key.id),
            name=api_key.name,
            revoked_by=request.user.username,
        )

        return Response(
            {
                'id': str(api_key.id),
                'name': api_key.name,
                'is_active': False,
                'detail': 'API key has been revoked.',
            },
            status=status.HTTP_200_OK,
        )


# ── Admin — Tenant Webhook Endpoints ───────────────────────────────────────────

class WebhookListView(APIView):
    """
    GET  /api/billing/admin/webhooks/
        List all webhook endpoints registered for the admin's organisation.
        The ``secret`` field is **never** returned after the initial creation
        response — store it securely at creation time.

    POST /api/billing/admin/webhooks/
        Register a new webhook endpoint.

        Expected body:
        {
            "url": "https://example.com/hooks/clinomic",
            "events": ["screening.completed", "screening.high_risk"]
        }

        The response includes the ``secret`` — this is the only time it is
        shown.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    throttle_classes = [AdminEndpointThrottle]
    required_roles = [Role.SUPER_ADMIN]

    _valid_events = frozenset(WebhookEndpoint.SUPPORTED_EVENTS)

    def get(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        endpoints = (
            WebhookEndpoint.objects
            .filter(organization=org)
            .order_by('-created_at')
        )

        data = [
            {
                'id': str(ep.id),
                'url': ep.url,
                'events': ep.events,
                'is_active': ep.is_active,
                'created_at': ep.created_at,
                'updated_at': ep.updated_at,
            }
            for ep in endpoints
        ]
        return Response(data)

    def post(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        url = (request.data.get('url') or '').strip()
        if not url:
            return Response({'error': '"url" is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # SSRF protection: require HTTPS and block private/internal IPs
        url_error = _validate_webhook_url(url)
        if url_error:
            return Response({'error': url_error}, status=status.HTTP_400_BAD_REQUEST)

        events = request.data.get('events', [])
        if not isinstance(events, list) or not events:
            return Response(
                {'error': '"events" must be a non-empty list.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invalid_events = [e for e in events if e not in self._valid_events]
        if invalid_events:
            return Response(
                {
                    'error': f'Invalid event(s): {invalid_events}. '
                             f'Valid events are: {sorted(self._valid_events)}.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        endpoint = WebhookEndpoint.objects.create(
            organization=org,
            url=url,
            events=events,
            is_active=True,
        )

        logger.info(
            'webhook_endpoint.created',
            org=org.name,
            endpoint_id=str(endpoint.id),
            url=url,
            events=events,
            created_by=request.user.username,
        )

        return Response(
            {
                'id': str(endpoint.id),
                'url': endpoint.url,
                'events': endpoint.events,
                'secret': endpoint.secret,   # shown ONCE — cannot be recovered later
                'is_active': endpoint.is_active,
                'created_at': endpoint.created_at,
                'warning': (
                    'Store this secret securely. It will not be shown again. '
                    'Use it to verify the X-Clinomic-Signature header on incoming requests.'
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class WebhookDetailView(APIView):
    """
    DELETE /api/billing/admin/webhooks/<uuid:pk>/
        Permanently remove a webhook endpoint registration.
        Future deliveries to this URL will immediately stop.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    throttle_classes = [AdminEndpointThrottle]
    required_roles = [Role.SUPER_ADMIN]

    def delete(self, request, pk):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            endpoint = WebhookEndpoint.objects.get(pk=pk, organization=org)
        except WebhookEndpoint.DoesNotExist:
            return Response({'error': 'Webhook endpoint not found.'}, status=status.HTTP_404_NOT_FOUND)

        endpoint_id = str(endpoint.id)
        endpoint_url = endpoint.url
        endpoint.delete()

        logger.info(
            'webhook_endpoint.deleted',
            org=org.name,
            endpoint_id=endpoint_id,
            url=endpoint_url,
            deleted_by=request.user.username,
        )

        return Response(
            {
                'id': endpoint_id,
                'detail': 'Webhook endpoint has been deleted.',
            },
            status=status.HTTP_200_OK,
        )

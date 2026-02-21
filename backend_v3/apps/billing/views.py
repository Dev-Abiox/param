"""
Billing API views.

SignupView              POST /api/signup/
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
import logging
import re
import secrets
from datetime import timedelta

import structlog
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core.models import Role
from apps.core.permissions import HasRole, IsMFAVerified

from .models import APIKey, PaymentEvent, SubscriptionPlan, TenantSubscription, UsageRecord, WebhookEndpoint, VALID_SCOPES
from .serializers import (
    OnboardingStatusSerializer,
    SignupSerializer,
    SubscriptionPlanSerializer,
    TenantSubscriptionSerializer,
    UsageRecordSerializer,
)

logger = structlog.get_logger(__name__)


# ── helpers ────────────────────────────────────────────────────────────────────

RESERVED_SCHEMAS = frozenset({
    'public', 'pg_catalog', 'pg_toast', 'information_schema',
})


def _slugify_org(name: str) -> str:
    """Convert an org name to a safe PostgreSQL schema name."""
    slug = re.sub(r'[^a-z0-9]', '_', name.strip().lower())
    slug = re.sub(r'_+', '_', slug).strip('_')
    slug = slug[:40] or 'org'
    if slug in RESERVED_SCHEMAS:
        slug = f'tenant_{slug}'
    return slug


# ── Signup ─────────────────────────────────────────────────────────────────────

class SignupView(APIView):
    """
    Self-service tenant signup.

    POST /api/signup/
    Creates a new Organisation, provisions its PostgreSQL schema,
    creates an ADMIN user, and issues a JWT so the admin is immediately
    logged in.
    """
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        org_name = data['org_name'].strip()
        admin_email = data['admin_email'].lower().strip()
        admin_password = data['admin_password']
        plan_name = data['plan']

        # Validate password strength (matches ResetPasswordView rules)
        try:
            validate_password(admin_password)
        except ValidationError as e:
            return Response({'error': list(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        # Derive a unique schema name
        schema_name = _slugify_org(org_name)

        from apps.core.models import Organization, Domain, User
        from apps.core.authentication import create_access_token, create_refresh_token
        from apps.core.views import _set_refresh_cookie

        # Uniqueness checks
        if Organization.objects.filter(schema_name=schema_name).exists():
            return Response(
                {'error': f'An organisation with that name already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if User.objects.filter(email__iexact=admin_email).exists():
            return Response(
                {'error': 'An account with that email already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate plan
        try:
            plan = SubscriptionPlan.objects.get(name=plan_name, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({'error': 'Invalid plan.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # 1. Create Organization — triggers auto_create_schema
                org = Organization.objects.create(
                    name=org_name,
                    schema_name=schema_name,
                    is_active=True,
                )

                # 2. Create a Domain for housekeeping
                Domain.objects.create(
                    tenant=org,
                    domain=f'{schema_name}.internal',
                    is_primary=True,
                )

                # 3. Create the admin User in the public schema
                username = admin_email.split('@')[0][:40]
                base_username = username
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f'{base_username}{counter}'
                    counter += 1

                user = User(
                    username=username,
                    email=admin_email,
                    name=org_name,
                    role=Role.ADMIN,
                    organization=org,
                    is_active=True,
                )
                user.set_password(admin_password)
                user.save()

                # 4. Create TenantSubscription (14-day trial)
                now = timezone.now()
                trial_end = now + timedelta(days=14)
                period_end = now + timedelta(days=30)
                TenantSubscription.objects.create(
                    organization=org,
                    plan=plan,
                    status=TenantSubscription.Status.TRIAL,
                    current_period_start=now,
                    current_period_end=period_end,
                    trial_end=trial_end,
                )
        except IntegrityError:
            return Response(
                {'error': 'An organisation or account with that name already exists.'},
                status=status.HTTP_409_CONFLICT,
            )

        # 5. Issue JWT tokens (mfa_verified=False — user must set up MFA separately)
        access_token = create_access_token(user, mfa_verified=False)
        refresh_token, _ = create_refresh_token(user)

        logger.info('signup.success', org=org.name, schema=org.schema_name, user=user.username)

        # 6. Fire welcome email asynchronously (non-blocking, best-effort)
        from apps.billing.tasks import send_welcome_email
        send_welcome_email.delay(
            user_id=str(user.id),
            org_name=org.name,
            plan_name=plan.display_name,
            trial_end_iso=trial_end.isoformat(),
        )

        response = Response({
            'access_token': access_token,
            'user': {
                'id': str(user.id),
                'name': user.name or user.username,
                'role': user.role,
            },
            'org': {
                'id': str(org.id),
                'name': org.name,
            },
            'plan': plan_name,
            'trial_end': trial_end.isoformat(),
        }, status=status.HTTP_201_CREATED)

        _set_refresh_cookie(response, refresh_token)
        return response


# ── Onboarding Status ──────────────────────────────────────────────────────────

class OnboardingStatusView(APIView):
    """
    PATCH /api/billing/onboarding/
    Allows the frontend wizard to mark steps as completed.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.ADMIN]

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


class WebhookView(APIView):
    """
    POST /api/billing/webhook/
    Receives Razorpay subscription webhook events, verifies the HMAC-SHA256
    signature, and updates TenantSubscription state accordingly.
    All raw events are stored in PaymentEvent for idempotency + audit.
    """
    permission_classes = [AllowAny]
    throttle_classes = [WebhookRateThrottle]

    def post(self, request):
        sig = request.headers.get('X-Razorpay-Signature', '')
        webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')

        # Fail closed: reject all webhooks when secret is not configured
        if not webhook_secret:
            logger.error('billing.webhook_secret_not_configured')
            return Response({'error': 'webhook not configured'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if webhook_secret:
            try:
                import razorpay
                client = razorpay.Client(
                    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
                )
                client.utility.verify_webhook_signature(
                    request.body.decode('utf-8'), sig, webhook_secret
                )
            except Exception:
                logger.warning('billing.webhook_invalid_signature')
                return Response({'error': 'invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data
        event_type = data.get('event', '')
        sub_entity = (
            data.get('payload', {})
            .get('subscription', {})
            .get('entity', {})
        )
        razorpay_sub_id = sub_entity.get('id', '')
        event_id = data.get('id') or f'{event_type}:{razorpay_sub_id}'

        # Idempotency — skip if already processed
        if PaymentEvent.objects.filter(razorpay_event_id=event_id).exists():
            return Response({'status': 'already_processed'})

        # Find matching subscription
        sub = (
            TenantSubscription.objects
            .filter(razorpay_sub_id=razorpay_sub_id)
            .select_related('organization')
            .first()
        )

        # Store the raw event
        pe = PaymentEvent.objects.create(
            organization=sub.organization if sub else None,
            razorpay_event_id=event_id,
            event_type=event_type,
            payload=data,
        )

        if sub:
            now = timezone.now()
            try:
                if event_type == 'subscription.activated':
                    sub.transition_to(TenantSubscription.Status.ACTIVE)
                    # If this activation is for a plan upgrade, update the plan FK.
                    rz_plan_id = sub_entity.get('plan_id', '')
                    if rz_plan_id:
                        new_plan = SubscriptionPlan.objects.filter(
                            razorpay_plan_id=rz_plan_id, is_active=True
                        ).first()
                        if new_plan and new_plan.pk != sub.plan_id:
                            sub.plan = new_plan
                    sub.save(update_fields=['status', 'plan', 'updated_at'])
                    from django.core.cache import cache
                    cache.delete(f'plan_limit_over:{sub.organization_id}')

                elif event_type == 'subscription.charged':
                    sub.current_period_count = 0
                    sub.current_period_start = now
                    sub.current_period_end = now + timedelta(days=30)
                    sub.save(update_fields=[
                        'current_period_count',
                        'current_period_start',
                        'current_period_end',
                        'updated_at',
                    ])
                    from django.core.cache import cache
                    cache.delete(f'plan_limit_over:{sub.organization_id}')

                elif event_type == 'subscription.cancelled':
                    sub.transition_to(TenantSubscription.Status.CANCELLED)
                    sub.cancelled_at = now
                    sub.save(update_fields=['status', 'cancelled_at', 'updated_at'])

                elif event_type == 'payment.failed':
                    sub.transition_to(TenantSubscription.Status.PAST_DUE)
                    sub.save(update_fields=['status', 'updated_at'])

                pe.processed = True
                pe.save(update_fields=['processed'])
                logger.info('billing.webhook_processed', event_type=event_type, sub_id=razorpay_sub_id)
            except Exception as exc:
                pe.error = str(exc)
                pe.save(update_fields=['error'])
                logger.error('billing.webhook_error', event_type=event_type, error=str(exc))

        return Response({'status': 'ok'})


# ── Admin — Usage ──────────────────────────────────────────────────────────────

class AdminUsageView(APIView):
    """
    GET /api/billing/admin/usage
    Returns current usage stats and 6-month history for the admin's org.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.ADMIN]

    def get(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sub = TenantSubscription.objects.select_related('plan').get(organization=org)
        except TenantSubscription.DoesNotExist:
            return Response({'error': 'No subscription found'}, status=status.HTTP_404_NOT_FOUND)

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
    required_roles = [Role.ADMIN]

    def get(self, request):
        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sub = TenantSubscription.objects.select_related('plan').get(organization=org)
        except TenantSubscription.DoesNotExist:
            return Response({'error': 'No subscription found'}, status=status.HTTP_404_NOT_FOUND)

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
    required_roles = [Role.ADMIN]

    def post(self, request):
        plan_name = (request.data.get('plan') or '').strip().lower()
        if not plan_name:
            return Response({'error': 'plan is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_plan = SubscriptionPlan.objects.get(name=plan_name, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({'error': f'Unknown plan: {plan_name}'}, status=status.HTTP_400_BAD_REQUEST)

        if not new_plan.razorpay_plan_id:
            return Response(
                {'error': f'Plan "{plan_name}" is not linked to a Razorpay plan.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sub = TenantSubscription.objects.get(organization=org)
        except TenantSubscription.DoesNotExist:
            return Response({'error': 'No subscription found'}, status=status.HTTP_404_NOT_FOUND)

        if sub.plan.name == plan_name:
            return Response({'error': 'Already on this plan.'}, status=status.HTTP_400_BAD_REQUEST)

        # Create a Razorpay subscription for the new plan
        import razorpay
        try:
            client = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
            )
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
    required_roles = [Role.ADMIN]

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
    required_roles = [Role.ADMIN]

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
    required_roles = [Role.ADMIN]

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
    required_roles = [Role.ADMIN]

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

"""
Billing API views.

SignupView            POST /api/signup/
WebhookView           POST /api/billing/webhook/
OnboardingStatusView  PATCH /api/billing/onboarding/
AdminUsageView        GET  /api/billing/admin/usage
AdminBillingView      GET  /api/billing/admin/billing
AdminBillingUpgradeView POST /api/billing/admin/billing/upgrade
"""

import logging
import re
from datetime import timedelta

import structlog
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core.models import Role
from apps.core.permissions import HasRole, IsMFAVerified

from .models import PaymentEvent, SubscriptionPlan, TenantSubscription, UsageRecord
from .serializers import (
    OnboardingStatusSerializer,
    SignupSerializer,
    SubscriptionPlanSerializer,
    TenantSubscriptionSerializer,
    UsageRecordSerializer,
)

logger = structlog.get_logger(__name__)


# ── helpers ────────────────────────────────────────────────────────────────────

def _slugify_org(name: str) -> str:
    """Convert an org name to a safe PostgreSQL schema name."""
    slug = re.sub(r'[^a-z0-9]', '_', name.strip().lower())
    slug = re.sub(r'_+', '_', slug).strip('_')
    return slug[:40] or 'org'


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

        # 1. Create Organization — triggers auto_create_schema which provisions the PG schema
        #    and runs all TENANT_APP migrations synchronously.
        org = Organization.objects.create(
            name=org_name,
            schema_name=schema_name,
            is_active=True,
        )

        # 2. Create a Domain for housekeeping (virtual internal domain per org)
        Domain.objects.create(
            tenant=org,
            domain=f'{schema_name}.internal',
            is_primary=True,
        )

        # 3. Create the admin User in the public schema
        username = admin_email.split('@')[0][:40]
        # Ensure username uniqueness
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

        # 5. Issue JWT tokens
        access_token = create_access_token(user, mfa_verified=True)
        refresh_token, _ = create_refresh_token(user)

        logger.info('signup.success', org=org.name, schema=org.schema_name, user=user.username)

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
                'schema_name': org.schema_name,
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

class WebhookView(APIView):
    """
    POST /api/billing/webhook/
    Receives Razorpay subscription webhook events, verifies the HMAC-SHA256
    signature, and updates TenantSubscription state accordingly.
    All raw events are stored in PaymentEvent for idempotency + audit.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        sig = request.headers.get('X-Razorpay-Signature', '')
        webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '')

        # Verify signature when the secret is configured
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
                    sub.status = TenantSubscription.Status.ACTIVE
                    sub.save(update_fields=['status', 'updated_at'])

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
                    sub.status = TenantSubscription.Status.CANCELLED
                    sub.cancelled_at = now
                    sub.save(update_fields=['status', 'cancelled_at', 'updated_at'])

                elif event_type == 'payment.failed':
                    sub.status = TenantSubscription.Status.PAST_DUE
                    sub.save(update_fields=['status', 'updated_at'])

                pe.processed = True
                pe.save(update_fields=['processed'])
                logger.info('billing.webhook_processed', event=event_type, sub_id=razorpay_sub_id)
            except Exception as exc:
                pe.error = str(exc)
                pe.save(update_fields=['error'])
                logger.error('billing.webhook_error', event=event_type, error=str(exc))

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
    Updates the plan in the DB (scaffold — no real Razorpay checkout).
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

        org = getattr(request.user, 'organization', None)
        if not org:
            return Response({'error': 'No organisation found'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            sub = TenantSubscription.objects.get(organization=org)
        except TenantSubscription.DoesNotExist:
            return Response({'error': 'No subscription found'}, status=status.HTTP_404_NOT_FOUND)

        old_plan = sub.plan.name
        sub.plan = new_plan
        if sub.status not in (TenantSubscription.Status.ACTIVE, TenantSubscription.Status.TRIAL):
            sub.status = TenantSubscription.Status.ACTIVE
        sub.save(update_fields=['plan', 'status', 'updated_at'])

        # Bust limit cache in case the new plan has a higher/lower limit
        from django.core.cache import cache
        cache.delete(f'plan_limit_over:{org.id}')

        logger.info('billing.plan_changed', org=org.name, old=old_plan, new=plan_name)
        return Response({
            'plan': new_plan.name,
            'display_name': new_plan.display_name,
            'monthly_limit': new_plan.monthly_limit,
            'status': sub.status,
        })

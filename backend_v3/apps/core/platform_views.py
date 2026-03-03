"""
Platform Super Admin API views.

All endpoints require SUPER_ADMIN role or is_superuser=True.
All billing/org models live in the public schema — PublicSchemaMixin forces public schema.

PlatformStatsView       GET  /api/v1/platform/stats/
PlatformOrgListView     GET  /api/v1/platform/orgs/
PlatformCreateOrgView   POST /api/v1/platform/orgs/create/
PlatformOrgDetailView   GET  /api/v1/platform/orgs/<schema_name>/
                        PATCH /api/v1/platform/orgs/<schema_name>/
PlatformOrgPlanView     POST /api/v1/platform/orgs/<schema_name>/plan/
PlatformOrgUsageView    GET  /api/v1/platform/orgs/<schema_name>/usage/
PlatformOrgUsersView    GET  /api/v1/platform/orgs/<schema_name>/users/
                        POST /api/v1/platform/orgs/<schema_name>/users/
"""

import re
import secrets
from datetime import date, timedelta

import structlog
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Q, Sum
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.models import (
    PaymentEvent,
    SubscriptionPlan,
    TenantSubscription,
    UsageRecord,
)
from apps.billing.serializers import (
    SubscriptionPlanSerializer,
    TenantSubscriptionSerializer,
    UsageRecordSerializer,
)

from .models import Domain, Organization, Role, User
from .permissions import IsMFAVerified, IsPlatformSuperAdmin

logger = structlog.get_logger(__name__)

_PLATFORM_PERMS = [IsAuthenticated, IsMFAVerified, IsPlatformSuperAdmin]


class PublicSchemaMixin:
    """Force all platform views to execute in the public schema.

    The JWT middleware may set the search_path to the superadmin's org schema
    (e.g. demo_lab). Platform views must run in 'public' because Organization,
    User, SubscriptionPlan, etc. are shared-schema models and django-tenants
    raises an error if you create a tenant outside the public schema.
    """

    def initial(self, request, *args, **kwargs):
        connection.set_schema_to_public()
        super().initial(request, *args, **kwargs)

RESERVED_SCHEMAS = frozenset({
    'public', 'pg_catalog', 'pg_toast', 'information_schema',
})


def _slugify(name: str) -> str:
    slug = re.sub(r'[^a-z0-9]', '_', name.strip().lower())
    slug = re.sub(r'_+', '_', slug).strip('_')
    slug = slug[:40] or 'org'
    if slug in RESERVED_SCHEMAS:
        slug = f'tenant_{slug}'
    return slug


def _first_of_month(dt=None):
    d = (dt or date.today()).replace(day=1)
    return d


# ── Stats ─────────────────────────────────────────────────────────────────────

class PlatformStatsView(PublicSchemaMixin, APIView):
    """
    GET /api/v1/platform/stats/
    Platform-wide metrics for the super admin dashboard.
    """
    permission_classes = _PLATFORM_PERMS

    def get(self, request):
        # All subscriptions in public schema
        subs = TenantSubscription.objects.select_related('plan', 'organization').all()

        total_orgs   = subs.count()
        active_orgs  = subs.filter(status=TenantSubscription.Status.ACTIVE).count()
        trial_orgs   = subs.filter(status=TenantSubscription.Status.TRIAL).count()
        suspended    = subs.filter(status='SUSPENDED').count()

        # MRR: sum of plan prices for all ACTIVE subscriptions
        mrr = (
            subs.filter(status=TenantSubscription.Status.ACTIVE)
            .aggregate(mrr=Sum('plan__price_monthly'))['mrr']
            or 0
        )

        # Total screenings this month across all orgs
        fom = _first_of_month()
        total_screenings = (
            UsageRecord.objects.filter(period_start=fom)
            .aggregate(total=Sum('screening_count'))['total']
            or 0
        )

        # Plan breakdown
        plan_counts = {}
        for sub in subs:
            pname = sub.plan.name if sub.plan else 'unknown'
            plan_counts[pname] = plan_counts.get(pname, 0) + 1

        return Response({
            'total_orgs': total_orgs,
            'active_orgs': active_orgs,
            'trial_orgs': trial_orgs,
            'suspended_orgs': suspended,
            'mrr_inr': float(mrr),
            'total_screenings_this_month': total_screenings,
            'plan_breakdown': plan_counts,
        })


# ── Org List ──────────────────────────────────────────────────────────────────

class PlatformOrgListView(PublicSchemaMixin, APIView):
    """
    GET /api/v1/platform/orgs/
    Paginated list of all organisations with subscription + usage snapshot.
    Query params: ?page=1&page_size=20&search=<name>&plan=<name>&status=<status>
    """
    permission_classes = _PLATFORM_PERMS

    def get(self, request):
        page      = max(1, int(request.query_params.get('page', 1)))
        page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))
        search    = request.query_params.get('search', '').strip()
        plan_filter   = request.query_params.get('plan', '')
        status_filter = request.query_params.get('status', '')

        qs = (
            TenantSubscription.objects
            .select_related('plan', 'organization')
            .order_by('-organization__created_at')
        )

        if search:
            qs = qs.filter(organization__name__icontains=search)
        if plan_filter:
            qs = qs.filter(plan__name=plan_filter)
        if status_filter:
            qs = qs.filter(status=status_filter)

        total = qs.count()
        offset = (page - 1) * page_size
        subs = qs[offset: offset + page_size]

        # Fetch admin emails in one query
        org_ids = [s.organization_id for s in subs]
        admin_emails = {
            u.organization_id: u.email
            for u in User.objects.filter(
                organization_id__in=org_ids,
                role=Role.LAB,
                is_active=True,
            ).only('organization_id', 'email')
        }

        # Fetch current month usage
        fom = _first_of_month()
        usage_map = {
            ur.organization_id: ur.screening_count
            for ur in UsageRecord.objects.filter(
                organization_id__in=org_ids,
                period_start=fom,
            )
        }

        results = []
        for sub in subs:
            org = sub.organization
            lim = sub.plan.monthly_limit if sub.plan else -1
            cnt = sub.current_period_count
            pct = round(cnt / lim * 100, 1) if lim > 0 else 0
            results.append({
                'id': str(org.id),
                'name': org.name,
                'schema_name': org.schema_name,
                'created_at': org.created_at,
                'admin_email': admin_emails.get(org.id),
                'subscription': {
                    'plan': sub.plan.name if sub.plan else None,
                    'plan_display': sub.plan.display_name if sub.plan else None,
                    'status': sub.status,
                    'current_count': cnt,
                    'monthly_limit': lim,
                    'pct_used': pct,
                    'trial_end': sub.trial_end,
                    'current_period_end': sub.current_period_end,
                },
            })

        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': results,
        })


# ── Create Org ────────────────────────────────────────────────────────────────

class PlatformCreateOrgView(PublicSchemaMixin, APIView):
    """
    POST /api/v1/platform/orgs/create/
    Body: { org_name, admin_email, admin_name, plan_name }

    Creates a new tenant org, admin user, and ACTIVE subscription.
    Sends a lab-created email with temporary password.
    """
    permission_classes = _PLATFORM_PERMS

    def post(self, request):
        org_name   = (request.data.get('org_name') or '').strip()
        admin_email = (request.data.get('admin_email') or '').strip().lower()
        admin_name  = (request.data.get('admin_name') or '').strip()
        plan_name   = (request.data.get('plan_name') or '').strip()

        # Validate required fields
        errors = {}
        if not org_name:
            errors['org_name'] = 'Organisation name is required.'
        if not admin_email:
            errors['admin_email'] = 'Admin email is required.'
        if not admin_name:
            errors['admin_name'] = 'Admin name is required.'
        if not plan_name:
            errors['plan_name'] = 'Plan name is required.'
        if errors:
            return Response({'errors': errors}, status=status.HTTP_400_BAD_REQUEST)

        schema_name = _slugify(org_name)

        # Uniqueness checks
        if Organization.objects.filter(schema_name=schema_name).exists():
            return Response(
                {'error': 'An organisation with that name already exists.'},
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
            available = list(SubscriptionPlan.objects.filter(is_active=True).values_list('name', flat=True))
            return Response(
                {'error': f'Invalid plan. Available: {available}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate a secure temporary password
        temp_password = secrets.token_urlsafe(12)

        try:
            with transaction.atomic():
                # 1. Create Organization (triggers auto_create_schema via django-tenants)
                org = Organization.objects.create(
                    name=org_name,
                    schema_name=schema_name,
                    is_active=True,
                )

                # 2. Create Domain
                Domain.objects.create(
                    tenant=org,
                    domain=f'{schema_name}.internal',
                    is_primary=True,
                )

                # 3. Derive unique username
                username_base = admin_email.split('@')[0][:40]
                username = username_base
                counter = 1
                while User.objects.filter(username=username).exists():
                    username = f'{username_base}{counter}'
                    counter += 1

                # 4. Create LAB manager user
                user = User(
                    username=username,
                    email=admin_email,
                    name=admin_name,
                    role=Role.LAB,
                    organization=org,
                    is_active=True,
                )
                user.set_password(temp_password)
                user.save()

                # 5. Create TenantSubscription (ACTIVE, no trial — super admin override)
                now = timezone.now()
                TenantSubscription.objects.create(
                    organization=org,
                    plan=plan,
                    status=TenantSubscription.Status.ACTIVE,
                    current_period_start=now,
                    current_period_end=now + timedelta(days=30),
                )

        except IntegrityError:
            return Response(
                {'error': 'An organisation or account with that name already exists.'},
                status=status.HTTP_409_CONFLICT,
            )

        logger.info(
            'platform.org_created',
            org=org.name,
            schema=org.schema_name,
            admin=admin_email,
            plan=plan_name,
            created_by=request.user.username,
        )

        # 6. Send credentials email asynchronously
        from apps.billing.tasks import send_lab_created_email
        send_lab_created_email.delay(
            user_id=str(user.id),
            org_name=org.name,
            plan_name=plan.display_name,
        )

        return Response({
            'id': str(org.id),
            'name': org.name,
            'schema_name': org.schema_name,
            'admin_email': admin_email,
            'plan': plan.display_name,
            'message': f'Organisation created. Login credentials sent to {admin_email}.',
        }, status=status.HTTP_201_CREATED)


# ── Org Detail ────────────────────────────────────────────────────────────────

class PlatformOrgDetailView(PublicSchemaMixin, APIView):
    """
    GET   /api/v1/platform/orgs/<schema_name>/   — Full org detail
    PATCH /api/v1/platform/orgs/<schema_name>/   — Suspend or reactivate

    PATCH body: { "action": "suspend" | "reactivate" }
    """
    permission_classes = _PLATFORM_PERMS

    def _get_org(self, schema_name):
        try:
            return Organization.objects.get(schema_name=schema_name)
        except Organization.DoesNotExist:
            return None

    def get(self, request, schema_name):
        org = self._get_org(schema_name)
        if not org:
            return Response({'error': 'Organisation not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            sub = TenantSubscription.objects.select_related('plan').get(organization=org)
        except TenantSubscription.DoesNotExist:
            sub = None

        # Users in this org
        users = User.objects.filter(organization=org).values(
            'id', 'username', 'email', 'name', 'role', 'is_active', 'created_at', 'last_login'
        )

        # Domain
        domain = Domain.objects.filter(tenant=org, is_primary=True).first()

        # 12-month usage history
        history = UsageRecord.objects.filter(organization=org).order_by('-period_start')[:12]

        # Payment events
        events = PaymentEvent.objects.filter(organization=org).order_by('-created_at')[:10].values(
            'id', 'event_type', 'processed', 'created_at'
        )

        return Response({
            'id': str(org.id),
            'name': org.name,
            'schema_name': org.schema_name,
            'is_active': org.is_active,
            'created_at': org.created_at,
            'domain': domain.domain if domain else None,
            'subscription': TenantSubscriptionSerializer(sub).data if sub else None,
            'usage_history': UsageRecordSerializer(history, many=True).data,
            'payment_events': list(events),
            'users': list(users),
        })

    def patch(self, request, schema_name):
        org = self._get_org(schema_name)
        if not org:
            return Response({'error': 'Organisation not found.'}, status=status.HTTP_404_NOT_FOUND)

        action = (request.data.get('action') or '').strip().lower()
        if action not in ('suspend', 'reactivate'):
            return Response(
                {'error': 'action must be "suspend" or "reactivate".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            sub = TenantSubscription.objects.get(organization=org)
        except TenantSubscription.DoesNotExist:
            return Response({'error': 'No subscription found.'}, status=status.HTTP_404_NOT_FOUND)

        if action == 'suspend':
            sub.status = 'SUSPENDED'
            org.is_active = False
        else:
            sub.status = TenantSubscription.Status.ACTIVE
            org.is_active = True

        sub.save(update_fields=['status'])
        org.save(update_fields=['is_active'])

        logger.info(
            'platform.org_status_changed',
            org=org.name,
            action=action,
            changed_by=request.user.username,
        )

        return Response({
            'id': str(org.id),
            'name': org.name,
            'status': sub.status,
            'is_active': org.is_active,
        })


# ── Org Plan Override ─────────────────────────────────────────────────────────

class PlatformOrgPlanView(PublicSchemaMixin, APIView):
    """
    POST /api/v1/platform/orgs/<schema_name>/plan/
    Body: { "plan": "professional" }

    Super admin direct plan change — no Razorpay required.
    """
    permission_classes = _PLATFORM_PERMS

    def post(self, request, schema_name):
        try:
            org = Organization.objects.get(schema_name=schema_name)
        except Organization.DoesNotExist:
            return Response({'error': 'Organisation not found.'}, status=status.HTTP_404_NOT_FOUND)

        plan_name = (request.data.get('plan') or '').strip()
        if not plan_name:
            return Response({'error': '"plan" is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_plan = SubscriptionPlan.objects.get(name=plan_name, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            available = list(SubscriptionPlan.objects.filter(is_active=True).values_list('name', flat=True))
            return Response(
                {'error': f'Invalid plan. Available: {available}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            sub = TenantSubscription.objects.get(organization=org)
        except TenantSubscription.DoesNotExist:
            return Response({'error': 'No subscription found.'}, status=status.HTTP_404_NOT_FOUND)

        old_plan_name = sub.plan.name if sub.plan else 'unknown'
        sub.plan = new_plan
        sub.status = TenantSubscription.Status.ACTIVE
        sub.save(update_fields=['plan', 'status'])

        # Log as a PaymentEvent for audit trail
        PaymentEvent.objects.create(
            organization=org,
            razorpay_event_id=f'platform_plan_change_{org.schema_name}_{timezone.now().timestamp()}',
            event_type='plan.changed_by_platform_admin',
            payload={
                'old_plan': old_plan_name,
                'new_plan': plan_name,
                'changed_by': request.user.username,
            },
            processed=True,
        )

        logger.info(
            'platform.plan_changed',
            org=org.name,
            old_plan=old_plan_name,
            new_plan=plan_name,
            changed_by=request.user.username,
        )

        return Response({
            'org': org.name,
            'plan': new_plan.display_name,
            'monthly_limit': new_plan.monthly_limit,
            'status': sub.status,
        })


# ── Org Usage ─────────────────────────────────────────────────────────────────

class PlatformOrgUsageView(PublicSchemaMixin, APIView):
    """
    GET /api/v1/platform/orgs/<schema_name>/usage/
    Last 12 months of usage history for one org.
    """
    permission_classes = _PLATFORM_PERMS

    def get(self, request, schema_name):
        try:
            org = Organization.objects.get(schema_name=schema_name)
        except Organization.DoesNotExist:
            return Response({'error': 'Organisation not found.'}, status=status.HTTP_404_NOT_FOUND)

        try:
            sub = TenantSubscription.objects.select_related('plan').get(organization=org)
        except TenantSubscription.DoesNotExist:
            return Response({'error': 'No subscription found.'}, status=status.HTTP_404_NOT_FOUND)

        history = UsageRecord.objects.filter(organization=org).order_by('-period_start')[:12]
        lim = sub.plan.monthly_limit if sub.plan else -1
        pct = (
            round(sub.current_period_count / lim * 100, 1)
            if lim > 0 else 0
        )

        return Response({
            'org': org.name,
            'plan': sub.plan.display_name if sub.plan else None,
            'monthly_limit': lim,
            'current_count': sub.current_period_count,
            'pct_used': pct,
            'period_start': sub.current_period_start,
            'period_end': sub.current_period_end,
            'status': sub.status,
            'history': UsageRecordSerializer(history, many=True).data,
        })


# ── Org Users ─────────────────────────────────────────────────────────────────

class PlatformOrgUsersView(PublicSchemaMixin, APIView):
    """
    GET  /api/v1/platform/orgs/<schema_name>/users/   — List org users
    POST /api/v1/platform/orgs/<schema_name>/users/   — Create user in org
    """
    permission_classes = _PLATFORM_PERMS

    def _get_org(self, schema_name):
        try:
            return Organization.objects.get(schema_name=schema_name)
        except Organization.DoesNotExist:
            return None

    def get(self, request, schema_name):
        org = self._get_org(schema_name)
        if not org:
            return Response({'error': 'Organisation not found.'}, status=status.HTTP_404_NOT_FOUND)

        users = list(
            User.objects.filter(organization=org)
            .order_by('role', 'name')
            .values('id', 'username', 'email', 'name', 'role', 'is_active', 'created_at', 'last_login')
        )
        return Response({'org': org.name, 'users': users})

    def post(self, request, schema_name):
        org = self._get_org(schema_name)
        if not org:
            return Response({'error': 'Organisation not found.'}, status=status.HTTP_404_NOT_FOUND)

        email    = (request.data.get('email') or '').strip().lower()
        name     = (request.data.get('name') or '').strip()
        role_str = (request.data.get('role') or Role.LAB).strip().upper()
        password = request.data.get('password', '')

        if not email:
            return Response({'error': '"email" is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if role_str not in (Role.LAB, Role.DOCTOR):
            return Response(
                {'error': 'role must be LAB or DOCTOR.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(email__iexact=email).exists():
            return Response({'error': 'An account with that email already exists.'}, status=status.HTTP_400_BAD_REQUEST)

        # Generate password if not provided
        if not password:
            password = secrets.token_urlsafe(12)

        try:
            validate_password(password)
        except ValidationError as e:
            return Response({'error': list(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        username_base = email.split('@')[0][:40]
        username = username_base
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f'{username_base}{counter}'
            counter += 1

        user = User(
            username=username,
            email=email,
            name=name,
            role=role_str,
            organization=org,
            is_active=True,
        )
        user.set_password(password)
        user.save()

        logger.info(
            'platform.user_created',
            org=org.name,
            user_email=email,
            role=role_str,
            created_by=request.user.username,
        )

        # Send credentials email asynchronously
        try:
            from apps.billing.tasks import send_credentials_email
            send_credentials_email.delay(str(user.id), org.name)
        except Exception as exc:
            logger.warning('send_credentials_email_failed user_id=%s error=%s', user.id, exc)

        return Response({
            'id': str(user.id),
            'username': user.username,
            'email': user.email,
            'name': user.name,
            'role': user.role,
            'message': f'User created. Login credentials sent to {email}.',
        }, status=status.HTTP_201_CREATED)

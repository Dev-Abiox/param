"""
Billing middleware for the Clinomic SaaS engine.

JWTTenantMiddleware  — identifies the tenant from the JWT's org_id claim and
                       switches the PostgreSQL search_path to that tenant's
                       schema, overriding the domain-based TenantMainMiddleware
                       selection.  All tenants share a single domain; the JWT
                       is the source of truth for tenant identity.

PlanLimitMiddleware  — rejects POST /api/screening/predict with HTTP 402 when
                       the organisation has exhausted its monthly screening quota.
                       The check is cached for 5 minutes per org to avoid a DB
                       round-trip on every prediction request.
"""

import logging

import jwt
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger(__name__)


def _extract_jwt_claims(request) -> dict:
    """
    Decode the Bearer token from the Authorization header and return
    relevant claims (org_id, is_super_admin), or empty dict if absent/invalid.
    """
    auth = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth.startswith('Bearer '):
        return {}
    token = auth[7:]
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return {
            'org_id': payload.get('org_id') or None,
            'is_super_admin': payload.get('is_super_admin', False),
        }
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return {}
    except Exception:
        logger.warning("JWTTenantMiddleware: unexpected error decoding token", exc_info=True)
        return {}


class JWTTenantMiddleware:
    """
    Override the domain-based tenant selection with the org_id embedded in
    the JWT.  This allows all organisations to share a single domain.

    Must be placed immediately after TenantMainMiddleware in MIDDLEWARE so
    that connection.tenant / request.tenant are overwritten before any view
    code runs.

    For SUPER_ADMIN users whose org resolves to the public schema, the
    middleware checks for an ``X-Org-Id`` header to select a target tenant.
    If no header is present, it auto-selects the first non-public tenant
    so that admin views can query tenant-specific tables.
    """

    # URL prefixes that require a tenant schema (labs, doctors, patients,
    # screenings tables).  Requests to these paths are rejected with 412
    # when no tenant organisation exists yet.
    _TENANT_SCOPED_PREFIXES = (
        '/api/screening/',
        '/api/v1/screening/',
        '/api/analytics/',
        '/api/v1/analytics/',
        '/api/notifications/',
        '/api/v1/notifications/',
        '/api/v1/admin/labs',
        '/api/v1/admin/doctors',
        '/api/v1/admin/users',
        '/api/admin/labs',
        '/api/admin/doctors',
        '/api/admin/users',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        claims = _extract_jwt_claims(request)
        org_id = claims.get('org_id')
        if org_id:
            from apps.core.models import Organization
            try:
                org = Organization.objects.get(id=org_id, is_active=True)
                connection.set_tenant(org)
                request.tenant = org

                # SUPER_ADMIN on public schema: resolve a real tenant so
                # tenant-specific tables (labs, doctors, etc.) are reachable.
                if org.schema_name == 'public' and claims.get('is_super_admin'):
                    target = self._resolve_target_tenant(request, Organization)
                    if target:
                        connection.set_tenant(target)
                        request.tenant = target
                    elif self._is_tenant_scoped_path(request.path):
                        return JsonResponse(
                            {
                                'error': 'No organization exists yet. '
                                         'Create one in Platform Admin first.',
                                'code': 'no_tenant',
                            },
                            status=412,
                        )

            except Organization.DoesNotExist:
                logger.warning("JWTTenantMiddleware: org_id %s not found", org_id)
            except Exception as exc:
                logger.error("JWTTenantMiddleware: failed to set tenant: %s", exc)
                # Fail fast — do not continue with potentially wrong schema
                return JsonResponse(
                    {'error': 'Tenant resolution failed. Please try again.'},
                    status=503,
                )
        return self.get_response(request)

    @classmethod
    def _is_tenant_scoped_path(cls, path):
        """Return True if the request path requires a tenant schema."""
        return any(path.startswith(p) for p in cls._TENANT_SCOPED_PREFIXES)

    @staticmethod
    def _resolve_target_tenant(request, Organization):
        """
        For SUPER_ADMIN, pick the tenant to operate in:
        1. Explicit ``X-Org-Id`` header (for future org-selector UI).
        2. Fall back to the first non-public active organisation.
        """
        header_org_id = request.META.get('HTTP_X_ORG_ID')
        if header_org_id:
            try:
                target = Organization.objects.get(id=header_org_id, is_active=True)
                if target.schema_name != 'public':
                    return target
            except Organization.DoesNotExist:
                logger.warning("JWTTenantMiddleware: X-Org-Id %s not found", header_org_id)

        # Auto-select the first non-public tenant
        return (
            Organization.objects
            .exclude(schema_name='public')
            .filter(is_active=True)
            .order_by('created_at')
            .first()
        )


class OrgRateLimitMiddleware:
    """
    Per-organisation rate limiting for API endpoints.

    Prevents a single org from monopolising shared resources by enforcing
    a per-minute request cap on screening endpoints.  Uses a sliding-window
    counter in Redis with a 60-second TTL.

    Limits are configurable via ORG_RATE_LIMIT_PER_MINUTE in settings
    (default: 120 requests/minute per org).
    """

    RATE_LIMITED_PREFIXES = (
        '/api/screening/',
        '/api/v1/screening/',
        '/api/analytics/',
        '/api/v1/analytics/',
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self.limit = getattr(settings, 'ORG_RATE_LIMIT_PER_MINUTE', 120)

    def __call__(self, request):
        if not any(request.path.startswith(p) for p in self.RATE_LIMITED_PREFIXES):
            return self.get_response(request)

        org = getattr(request, 'tenant', None)
        if not org or getattr(org, 'schema_name', 'public') == 'public':
            return self.get_response(request)

        cache_key = f'org_ratelimit:{org.id}'
        try:
            current = cache.get(cache_key, 0)
            if current >= self.limit:
                logger.warning('org_rate_limit_exceeded: org=%s count=%s', org.id, current)
                return JsonResponse(
                    {'error': 'Rate limit exceeded. Please slow down requests.'},
                    status=429,
                )
            cache.set(cache_key, current + 1, timeout=60)
        except Exception:
            pass  # Redis down — allow the request through

        return self.get_response(request)


class PlanLimitMiddleware:
    """
    Enforce monthly screening quotas.

    Intercepts POST /api/screening/predict (and the /api/v1/ variant).
    When the tenant's current_period_count has reached or exceeded the plan
    limit, returns HTTP 402 immediately — the view is never called.

    The over-limit flag is cached per org for 60 seconds; it is busted by the
    billing.increment_usage Celery task whenever the counter changes.

    On DB errors the middleware fails closed (blocks the request) and does NOT
    cache the error result, so a transient DB issue does not persist as a
    5-minute outage.
    """

    PREDICT_PATHS = frozenset([
        '/api/screening/predict',
        '/api/v1/screening/predict',
    ])

    CACHE_TTL = 10  # seconds — short to minimize quota bypass window

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path.rstrip('/').lower()
        if request.method == 'POST' and path in self.PREDICT_PATHS:
            org = getattr(request, 'tenant', None)
            if org and getattr(org, 'schema_name', 'public') != 'public':
                blocked, reason = self._is_blocked(org)
                if blocked:
                    return JsonResponse(
                        {'error': reason},
                        status=402,
                    )
        return self.get_response(request)

    _REASON_EXPIRED = 'Your trial has expired. Please upgrade to a paid plan to continue screening.'
    _REASON_CANCELLED = 'Your subscription is cancelled. Please reactivate to continue screening.'
    _REASON_LIMIT = 'Monthly screening limit reached. Please upgrade your plan.'

    def _is_blocked(self, org) -> tuple[bool, str]:
        """Return (blocked: bool, reason: str)."""
        cache_key = f'plan_limit_over:{org.id}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        from apps.billing.models import TenantSubscription
        try:
            sub = TenantSubscription.objects.select_related('plan').get(organization=org)

            # Block screenings for expired or cancelled subscriptions
            if sub.status == TenantSubscription.Status.EXPIRED:
                result = (True, self._REASON_EXPIRED)
            elif sub.status == TenantSubscription.Status.CANCELLED:
                result = (True, self._REASON_CANCELLED)
            # Auto-expire trial if past trial_end (belt-and-suspenders
            # alongside the Celery beat task)
            elif (
                sub.status == TenantSubscription.Status.TRIAL
                and sub.trial_end
                and sub.trial_end <= timezone.now()
            ):
                try:
                    from django.db import transaction as db_tx
                    sub.transition_to(TenantSubscription.Status.EXPIRED)
                    with db_tx.atomic():
                        sub.save(update_fields=['status', 'updated_at'])
                    logger.info('PlanLimitMiddleware: auto-expired trial for org %s', org.id)
                except ValueError:
                    pass
                result = (True, self._REASON_EXPIRED)
            else:
                lim = sub.plan.monthly_limit
                over = lim != -1 and sub.current_period_count >= lim
                result = (True, self._REASON_LIMIT) if over else (False, '')
        except TenantSubscription.DoesNotExist:
            result = (False, '')
        except Exception:
            logger.error('PlanLimitMiddleware: DB error checking limit for org %s', org.id, exc_info=True)
            return (True, self._REASON_LIMIT)  # fail closed — do NOT cache error state

        cache.set(cache_key, result, timeout=self.CACHE_TTL)
        return result

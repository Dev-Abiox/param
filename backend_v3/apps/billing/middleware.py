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

logger = logging.getLogger(__name__)


def _extract_org_id(request) -> str | None:
    """
    Decode the Bearer token from the Authorization header and return the
    `org_id` claim, or None if the header is absent / token is invalid / expired.
    """
    auth = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth[7:]
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload.get('org_id') or None
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None
    except Exception:
        logger.warning("JWTTenantMiddleware: unexpected error decoding token", exc_info=True)
        return None


class JWTTenantMiddleware:
    """
    Override the domain-based tenant selection with the org_id embedded in
    the JWT.  This allows all organisations to share a single domain.

    Must be placed immediately after TenantMainMiddleware in MIDDLEWARE so
    that connection.tenant / request.tenant are overwritten before any view
    code runs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        org_id = _extract_org_id(request)
        if org_id:
            from apps.core.models import Organization
            try:
                org = Organization.objects.get(id=org_id, is_active=True)
                connection.set_tenant(org)
                request.tenant = org
            except Organization.DoesNotExist:
                logger.warning("JWTTenantMiddleware: org_id %s not found", org_id)
            except Exception as exc:
                logger.error("JWTTenantMiddleware: failed to set tenant: %s", exc)
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
                over = self._is_over_limit(org)
                if over:
                    return JsonResponse(
                        {'error': 'Monthly screening limit reached. Please upgrade your plan.'},
                        status=402,
                    )
        return self.get_response(request)

    def _is_over_limit(self, org) -> bool:
        cache_key = f'plan_limit_over:{org.id}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        from apps.billing.models import TenantSubscription
        try:
            sub = TenantSubscription.objects.select_related('plan').get(organization=org)
            lim = sub.plan.monthly_limit
            over = lim != -1 and sub.current_period_count >= lim
        except TenantSubscription.DoesNotExist:
            over = False
        except Exception:
            logger.error('PlanLimitMiddleware: DB error checking limit for org %s', org.id, exc_info=True)
            return True  # fail closed — do NOT cache error state

        cache.set(cache_key, over, timeout=self.CACHE_TTL)
        return over

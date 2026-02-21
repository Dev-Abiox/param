"""
URL configuration for Clinomic B12 Screening Platform.

Route structure
───────────────
  /api/v1/          ← current versioned routes  (preferred)
  /api/             ← legacy routes              (backward-compatible)
  /api/docs/        ← Swagger UI
  /api/redoc/       ← ReDoc UI
  /api/schema/      ← raw OpenAPI schema (JSON/YAML)
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.billing.urls import signup_urlpatterns

urlpatterns = [
    path('admin/', admin.site.urls),

    # ── Prometheus metrics (internal — restrict at nginx/firewall level) ────────
    path('', include('django_prometheus.urls')),

    # ── API v1 (versioned — preferred) ────────────────────────────────────────
    path('api/v1/', include('apps.core.urls')),
    path('api/v1/screening/', include('apps.screening.urls')),
    path('api/v1/analytics/', include('apps.analytics.urls')),
    path('api/v1/billing/', include('apps.billing.urls')),
    path('api/v1/', include(signup_urlpatterns)),
    path('api/v1/admin/', include('apps.core.admin_urls')),
    path('api/v1/platform/', include('apps.core.platform_urls')),

    # ── API legacy (unversioned — backward-compatible) ─────────────────────────
    path('api/', include('apps.core.urls')),
    path('api/screening/', include('apps.screening.urls')),
    path('api/analytics/', include('apps.analytics.urls')),
    path('api/billing/', include('apps.billing.urls')),
    path('api/', include(signup_urlpatterns)),
    path('api/admin/', include('apps.core.admin_urls')),
    path('api/platform/', include('apps.core.platform_urls')),

    # ── OpenAPI / Docs ─────────────────────────────────────────────────────────
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Health (also accessible at root for load-balancer probes)
    path('', include('apps.core.urls')),
]

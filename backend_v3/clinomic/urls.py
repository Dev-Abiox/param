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

urlpatterns = [
    path('admin/', admin.site.urls),

    # ── API v1 (versioned — preferred) ────────────────────────────────────────
    path('api/v1/', include('apps.core.urls')),
    path('api/v1/screening/', include('apps.screening.urls')),
    path('api/v1/analytics/', include('apps.analytics.urls')),

    # ── API legacy (unversioned — backward-compatible) ─────────────────────────
    path('api/', include('apps.core.urls')),
    path('api/screening/', include('apps.screening.urls')),
    path('api/analytics/', include('apps.analytics.urls')),

    # ── OpenAPI / Docs ─────────────────────────────────────────────────────────
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),

    # Health (also accessible at root for load-balancer probes)
    path('', include('apps.core.urls')),
]

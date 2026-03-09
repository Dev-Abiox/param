"""
Platform Super Admin URL configuration.
Included at /api/v1/platform/ and /api/platform/ in clinomic/urls.py.
"""
from django.urls import path

from .platform_views import (
    PlatformCreateOrgView,
    PlatformOrgDetailView,
    PlatformOrgListView,
    PlatformOrgPlanView,
    PlatformOrgUsageView,
    PlatformOrgUsersView,
    PlatformResendCredentialsView,
    PlatformStatsView,
)

urlpatterns = [
    path('stats/',                            PlatformStatsView.as_view(),      name='platform-stats'),
    path('orgs/',                             PlatformOrgListView.as_view(),    name='platform-orgs'),
    path('orgs/create/',                      PlatformCreateOrgView.as_view(),  name='platform-org-create'),
    path('orgs/<str:schema_name>/',           PlatformOrgDetailView.as_view(),  name='platform-org-detail'),
    path('orgs/<str:schema_name>/plan/',      PlatformOrgPlanView.as_view(),    name='platform-org-plan'),
    path('orgs/<str:schema_name>/usage/',     PlatformOrgUsageView.as_view(),   name='platform-org-usage'),
    path('orgs/<str:schema_name>/users/',     PlatformOrgUsersView.as_view(),   name='platform-org-users'),
    path('orgs/<str:schema_name>/users/<uuid:user_id>/resend-credentials/', PlatformResendCredentialsView.as_view(), name='platform-resend-credentials'),
]

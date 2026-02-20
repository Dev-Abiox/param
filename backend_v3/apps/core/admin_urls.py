"""
Consolidated admin routes — all admin endpoints under /api/admin/ (and /api/v1/admin/).

This module re-exports views from core, screening, and billing so that every
admin endpoint is reachable through a single, consistent prefix.  The original
per-app routes remain for backward compatibility.
"""

from django.urls import path

from apps.billing.views import (
    AdminBillingUpgradeView,
    AdminBillingView,
    AdminUsageView,
)
from apps.core.views import AdminUserDetailView, AdminUserListView
from apps.screening.views import (
    AdminDoctorDetailView,
    AdminDoctorView,
    AdminLabDetailView,
    AdminLabView,
)

urlpatterns = [
    # User Management
    path('users', AdminUserListView.as_view(), name='admin-consolidated-users'),
    path('users/<uuid:user_id>', AdminUserDetailView.as_view(), name='admin-consolidated-user-detail'),

    # Lab Management
    path('labs', AdminLabView.as_view(), name='admin-consolidated-labs'),
    path('labs/<uuid:lab_id>', AdminLabDetailView.as_view(), name='admin-consolidated-lab-detail'),

    # Doctor Management
    path('doctors', AdminDoctorView.as_view(), name='admin-consolidated-doctors'),
    path('doctors/<uuid:doctor_id>', AdminDoctorDetailView.as_view(), name='admin-consolidated-doctor-detail'),

    # Billing
    path('usage/', AdminUsageView.as_view(), name='admin-consolidated-usage'),
    path('billing/', AdminBillingView.as_view(), name='admin-consolidated-billing'),
    path('billing/upgrade/', AdminBillingUpgradeView.as_view(), name='admin-consolidated-upgrade'),
]

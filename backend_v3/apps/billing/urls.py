"""
Billing URL configuration.

Routes are included at both /api/billing/ and /api/v1/billing/ in clinomic/urls.py.
The signup endpoint is also wired at /api/signup/ (legacy) and /api/v1/signup/.
"""

from django.urls import path

from .views import (
    AdminBillingUpgradeView,
    AdminBillingView,
    AdminUsageView,
    OnboardingStatusView,
    SignupView,
    WebhookView,
)

urlpatterns = [
    # Razorpay webhook
    path('webhook/', WebhookView.as_view(), name='billing-webhook'),

    # Onboarding wizard status
    path('onboarding/', OnboardingStatusView.as_view(), name='billing-onboarding'),

    # Admin portal — usage & billing
    path('admin/usage/', AdminUsageView.as_view(), name='billing-admin-usage'),
    path('admin/billing/', AdminBillingView.as_view(), name='billing-admin-billing'),
    path('admin/upgrade/', AdminBillingUpgradeView.as_view(), name='billing-admin-upgrade'),
]

# Standalone signup (also included at /api/signup/ in the root urls.py)
signup_urlpatterns = [
    path('signup/', SignupView.as_view(), name='billing-signup'),
]

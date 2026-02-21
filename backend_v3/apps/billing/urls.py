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
    APIKeyDetailView,
    APIKeyListView,
    OnboardingStatusView,
    SignupView,
    WebhookDetailView,
    WebhookListView,
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

    # Admin portal — API key management
    path('admin/api-keys/', APIKeyListView.as_view(), name='billing-admin-api-keys'),
    path('admin/api-keys/<uuid:pk>/', APIKeyDetailView.as_view(), name='billing-admin-api-key-detail'),

    # Admin portal — tenant webhook endpoint management
    path('admin/webhooks/', WebhookListView.as_view(), name='billing-admin-webhooks'),
    path('admin/webhooks/<uuid:pk>/', WebhookDetailView.as_view(), name='billing-admin-webhook-detail'),
]

# Standalone signup (also included at /api/signup/ in the root urls.py)
signup_urlpatterns = [
    path('signup/', SignupView.as_view(), name='billing-signup'),
]

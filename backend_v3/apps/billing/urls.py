"""
Billing URL configuration.

Routes are included at both /api/billing/ and /api/v1/billing/ in clinomic/urls.py.
"""

from django.urls import path

from .views import (
    AdminBillingUpgradeView,
    AdminBillingView,
    AdminUsageView,
    APIKeyDetailView,
    APIKeyListView,
    OnboardingStatusView,
    PaymentVerifyView,
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
    path('admin/verify-payment/', PaymentVerifyView.as_view(), name='billing-admin-verify-payment'),

    # Admin portal — API key management
    path('admin/api-keys/', APIKeyListView.as_view(), name='billing-admin-api-keys'),
    path('admin/api-keys/<uuid:pk>/', APIKeyDetailView.as_view(), name='billing-admin-api-key-detail'),

    # Admin portal — tenant webhook endpoint management
    path('admin/webhooks/', WebhookListView.as_view(), name='billing-admin-webhooks'),
    path('admin/webhooks/<uuid:pk>/', WebhookDetailView.as_view(), name='billing-admin-webhook-detail'),
]

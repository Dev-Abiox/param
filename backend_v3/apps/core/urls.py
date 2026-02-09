"""
URL configuration for Core API.
"""

from django.urls import path

from .views import (
    HealthLiveView,
    HealthReadyView,
    LoginView,
    LogoutView,
    MeView,
    MFABackupCodesView,
    MFADisableView,
    MFASetupView,
    MFAStatusView,
    MFAVerifySetupView,
    MFAVerifyView,
    TokenRefreshView,
)

urlpatterns = [
    # Authentication
    path('auth/login', LoginView.as_view(), name='auth-login'),
    path('auth/mfa/verify', MFAVerifyView.as_view(), name='auth-mfa-verify'),
    path('auth/refresh', TokenRefreshView.as_view(), name='auth-refresh'),
    path('auth/logout', LogoutView.as_view(), name='auth-logout'),
    path('auth/me', MeView.as_view(), name='auth-me'),

    # MFA Management
    path('mfa/setup', MFASetupView.as_view(), name='mfa-setup'),
    path('mfa/verify-setup', MFAVerifySetupView.as_view(), name='mfa-verify-setup'),
    path('mfa/status', MFAStatusView.as_view(), name='mfa-status'),
    path('mfa/disable', MFADisableView.as_view(), name='mfa-disable'),
    path('mfa/backup-codes/regenerate', MFABackupCodesView.as_view(), name='mfa-backup-codes'),

    # Health Checks
    path('health/live', HealthLiveView.as_view(), name='health-live'),
    path('health/ready', HealthReadyView.as_view(), name='health-ready'),
]

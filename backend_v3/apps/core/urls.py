"""
URL configuration for Core API.
"""

from django.urls import path
from django.http import JsonResponse

from .views import (
    AdminUserDetailView,
    AdminUserListView,
    ForgotPasswordView,
    HealthLiveView,
    HealthReadyView,
    HealthView,
    LoginView,
    LogoutView,
    MeView,
    MFABackupCodesView,
    MFADisableView,
    MFASetupView,
    MFAStatusView,
    MFAVerifySetupView,
    MFAVerifyView,
    NotificationListView,
    NotificationMarkReadView,
    ResetPasswordView,
    SessionListView,
    SessionRevokeView,
    TokenRefreshView,
    health,
)

urlpatterns = [
    # Authentication
    path('auth/login', LoginView.as_view(), name='auth-login'),
    path('auth/mfa/verify', MFAVerifyView.as_view(), name='auth-mfa-verify'),
    path('auth/refresh', TokenRefreshView.as_view(), name='auth-refresh'),
    path('auth/logout', LogoutView.as_view(), name='auth-logout'),
    path('auth/me', MeView.as_view(), name='auth-me'),

    # Password Reset
    path('auth/forgot-password', ForgotPasswordView.as_view(), name='auth-forgot-password'),
    path('auth/reset-password', ResetPasswordView.as_view(), name='auth-reset-password'),

    # Session Management
    path('auth/sessions', SessionListView.as_view(), name='auth-sessions'),
    path('auth/sessions/<uuid:token_id>', SessionRevokeView.as_view(), name='auth-session-revoke'),

    # MFA Management
    path('mfa/setup', MFASetupView.as_view(), name='mfa-setup'),
    path('mfa/verify-setup', MFAVerifySetupView.as_view(), name='mfa-verify-setup'),
    path('mfa/status', MFAStatusView.as_view(), name='mfa-status'),
    path('mfa/disable', MFADisableView.as_view(), name='mfa-disable'),
    path('mfa/backup-codes/regenerate', MFABackupCodesView.as_view(), name='mfa-backup-codes'),

    # Notifications
    path('notifications/', NotificationListView.as_view(), name='notifications-list'),
    path('notifications/<uuid:notification_id>/read', NotificationMarkReadView.as_view(), name='notifications-read'),

    # Admin — User Management
    path('admin/users', AdminUserListView.as_view(), name='admin-users'),
    path('admin/users/<uuid:user_id>', AdminUserDetailView.as_view(), name='admin-user-detail'),

    # Health Checks
    path('health/live', HealthLiveView.as_view(), name='health-live'),
    path('health/ready', HealthReadyView.as_view(), name='health-ready'),
    path('health/', HealthView.as_view(), name='health'),
    path('api/health/', health, name='api-health'),
]

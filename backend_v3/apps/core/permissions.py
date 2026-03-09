"""
Role-based permissions for Clinomic API.
"""

from django.conf import settings as django_settings
from django.utils import timezone as dj_tz
from rest_framework import permissions

from .models import MFASettings, Role

# Grace period (in hours) before MFA setup becomes mandatory for required roles.
MFA_GRACE_PERIOD_HOURS = 24


class IsAdmin(permissions.BasePermission):
    """Allow SUPER_ADMIN or Django superuser only."""
    message = 'Admin access required.'

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            (request.user.role == Role.SUPER_ADMIN
             or request.user.is_superuser)
        )


class IsLabOrDoctor(permissions.BasePermission):
    """Allow lab technicians and doctors."""
    message = 'Lab or Doctor access required.'

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role in [Role.LAB, Role.DOCTOR, Role.SUPER_ADMIN]
        )


class IsOrgManager(permissions.BasePermission):
    """SUPER_ADMIN or LAB can manage their organization."""
    message = 'Organization management access required.'

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            (request.user.role in (Role.SUPER_ADMIN, Role.LAB)
             or request.user.is_superuser)
        )


class IsDoctor(permissions.BasePermission):
    """Only allow doctors."""
    message = 'Doctor access required.'

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            (request.user.role == Role.DOCTOR or request.user.is_superuser)
        )


class HasRole(permissions.BasePermission):
    """
    Dynamic role permission check.

    Usage in views:
        permission_classes = [HasRole]
        required_roles = [Role.LAB]
    """
    message = 'Insufficient permissions.'

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        required_roles = getattr(view, 'required_roles', [])
        if not required_roles:
            return True

        return request.user.role in required_roles


class IsPlatformSuperAdmin(permissions.BasePermission):
    """Only the SaaS platform owner (SUPER_ADMIN role or is_superuser) may access."""
    message = 'Platform administrator access required.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_superuser or request.user.role == Role.SUPER_ADMIN)
        )


class HasAPIKeyScope(permissions.BasePermission):
    """
    When a request is authenticated via an API key, enforce that the key has
    the required scope declared on the view as `required_api_key_scope`.

    JWT-authenticated requests (browser sessions) bypass this check entirely —
    scopes only apply to programmatic API key access.

    Usage:
        class MyView(APIView):
            permission_classes = [IsAuthenticated, IsMFAVerified, HasAPIKeyScope]
            required_api_key_scope = 'screening:write'
    """
    message = 'API key does not have the required scope for this action.'

    def has_permission(self, request, view):
        api_key = getattr(request, 'api_key', None)
        if api_key is None:
            # JWT-authenticated — no scope restriction
            return True
        required_scope = getattr(view, 'required_api_key_scope', None)
        if required_scope is None:
            return True
        return api_key.has_scope(required_scope)


class IsMFAVerified(permissions.BasePermission):
    """
    Require MFA verification for sensitive operations.

    If the user has not enabled MFA yet, access is always granted — the
    frontend is responsible for redirecting to MFA setup.  Once MFA is
    enabled, the JWT must contain ``mfa_verified=True``.
    """
    message = 'MFA verification required.'

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        # If user hasn't set up MFA yet, allow access unconditionally.
        # The frontend handles redirecting to /settings for MFA setup.
        try:
            mfa_settings = request.user.mfa_settings
        except MFASettings.DoesNotExist:
            mfa_settings = None

        if mfa_settings is None or not mfa_settings.is_enabled:
            return True

        # MFA is enabled — require mfa_verified claim in the token
        token_payload = getattr(request, 'token_payload', {})
        return token_payload.get('mfa_verified', False)

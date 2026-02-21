"""
Role-based permissions for Clinomic API.
"""

from rest_framework import permissions

from .models import Role


class IsAdmin(permissions.BasePermission):
    """Only allow admin users."""
    message = 'Admin access required.'

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            (request.user.role == Role.ADMIN or request.user.is_superuser)
        )


class IsLabOrDoctor(permissions.BasePermission):
    """Allow lab technicians and doctors."""
    message = 'Lab or Doctor access required.'

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated and
            request.user.role in [Role.LAB, Role.DOCTOR, Role.ADMIN]
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
        required_roles = [Role.ADMIN, Role.LAB]
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
    """
    message = 'MFA verification required.'

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        token_payload = getattr(request, 'token_payload', {})
        return token_payload.get('mfa_verified', False)

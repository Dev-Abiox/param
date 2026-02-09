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

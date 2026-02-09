"""
Custom exception handling for Clinomic API.
"""

import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class MLModelNotReadyError(Exception):
    """Raised when ML models are not ready for inference."""
    pass


class TenantAccessError(Exception):
    """Raised when tenant isolation is violated."""
    pass


def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF.

    Provides consistent error response format and logging.
    """
    # Call DRF's default exception handler first
    response = exception_handler(exc, context)

    # Handle custom exceptions
    if isinstance(exc, MLModelNotReadyError):
        logger.error(f"ML model not ready: {exc}")
        return Response(
            {'error': 'ML screening service unavailable', 'detail': str(exc)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    if isinstance(exc, TenantAccessError):
        logger.warning(f"Tenant access violation: {exc}")
        return Response(
            {'error': 'Access denied', 'detail': 'You do not have access to this resource'},
            status=status.HTTP_403_FORBIDDEN
        )

    # Log unhandled exceptions
    if response is None:
        logger.exception(f"Unhandled exception: {exc}")
        return Response(
            {'error': 'Internal server error'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    # Enhance error response format
    if response is not None:
        error_data = {
            'error': response.data.get('detail', 'Error'),
        }
        if isinstance(response.data, dict):
            error_data.update({k: v for k, v in response.data.items() if k != 'detail'})
        response.data = error_data

    return response

"""
Custom exception handling for Clinomic API.

Never leak internal error details (file paths, stack traces, DB errors)
to API consumers. Log the full error server-side and return a generic
message with a correlation_id so support can trace the issue.
"""

import structlog

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = structlog.get_logger(__name__)


class MLModelNotReadyError(Exception):
    """Raised when ML models are not ready for inference."""
    pass


class TenantAccessError(Exception):
    """Raised when tenant isolation is violated."""
    pass


def _get_correlation_id(context):
    """Extract correlation_id from the request if available."""
    request = context.get('request')
    return getattr(request, 'correlation_id', None) if request else None


def custom_exception_handler(exc, context):
    """
    Custom exception handler for DRF.

    Provides consistent error response format, never leaks internals.
    """
    correlation_id = _get_correlation_id(context)

    # Call DRF's default exception handler first
    response = exception_handler(exc, context)

    # Handle custom exceptions
    if isinstance(exc, MLModelNotReadyError):
        logger.error("ml_model_not_ready", error=str(exc), correlation_id=correlation_id)
        return Response(
            {'error': 'ML screening service temporarily unavailable', 'correlation_id': correlation_id},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )

    if isinstance(exc, TenantAccessError):
        logger.warning("tenant_access_violation", error=str(exc), correlation_id=correlation_id)
        return Response(
            {'error': 'Access denied', 'correlation_id': correlation_id},
            status=status.HTTP_403_FORBIDDEN
        )

    # Log unhandled exceptions — never expose details to client
    if response is None:
        logger.exception("unhandled_exception", error=str(exc), correlation_id=correlation_id)
        return Response(
            {'error': 'Internal server error', 'correlation_id': correlation_id},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    # Enhance DRF error responses — strip internal details
    if response is not None:
        if isinstance(response.data, dict):
            error_data = {
                'error': response.data.get('detail', 'Error'),
                'correlation_id': correlation_id,
            }
            # Preserve field-level validation errors (safe to expose)
            field_errors = {
                k: v for k, v in response.data.items()
                if k not in ('detail', 'error', 'correlation_id')
            }
            if field_errors:
                error_data['fields'] = field_errors
            response.data = error_data
        else:
            response.data = {
                'error': str(response.data) if response.data else 'Error',
                'correlation_id': correlation_id,
            }

    return response

"""
Tests for CorrelationIdMiddleware — request ID injection and structlog binding.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.http import HttpResponse
from django.test import RequestFactory


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def middleware():
    from apps.core.middleware import CorrelationIdMiddleware
    inner = MagicMock(return_value=HttpResponse('ok'))
    return CorrelationIdMiddleware(inner)


class TestCorrelationIdMiddleware:

    def test_generates_request_id_when_missing(self, rf, middleware):
        """Should generate a UUID4 request_id when no header is present."""
        request = rf.get('/api/test')

        response = middleware(request)

        assert hasattr(request, 'request_id')
        # Validate it's a valid UUID
        uuid.UUID(request.request_id)
        assert response['X-Request-ID'] == request.request_id

    def test_uses_existing_request_id(self, rf, middleware):
        """Should use the incoming X-Request-ID header if present."""
        existing_id = 'req-abc-123'
        request = rf.get('/api/test')
        request.META['HTTP_X_REQUEST_ID'] = existing_id

        response = middleware(request)

        assert request.request_id == existing_id
        assert response['X-Request-ID'] == existing_id

    def test_binds_structlog_contextvars(self, rf):
        """Should bind request_id into structlog context."""
        from apps.core.middleware import CorrelationIdMiddleware

        with patch('apps.core.middleware.structlog') as mock_structlog:
            inner = MagicMock(return_value=HttpResponse('ok'))
            mw = CorrelationIdMiddleware(inner)
            request = rf.get('/api/test')
            mw(request)

        mock_structlog.contextvars.clear_contextvars.assert_called_once()
        mock_structlog.contextvars.bind_contextvars.assert_called_once_with(
            request_id=request.request_id
        )

    def test_passes_request_to_inner(self, rf):
        """Should call the inner get_response and return its result."""
        from apps.core.middleware import CorrelationIdMiddleware

        inner_response = HttpResponse('ok')
        inner = MagicMock(return_value=inner_response)
        mw = CorrelationIdMiddleware(inner)

        request = rf.get('/api/test')
        response = mw(request)

        inner.assert_called_once_with(request)
        assert response == inner_response

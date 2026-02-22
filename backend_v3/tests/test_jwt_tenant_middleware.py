"""
Tests for JWTTenantMiddleware — maps JWT org_id claim to tenant schema.
"""

import uuid
from unittest.mock import MagicMock, patch

import jwt
import pytest
from django.conf import settings
from django.test import RequestFactory


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def middleware():
    from apps.billing.middleware import JWTTenantMiddleware
    inner = MagicMock(return_value='ok')
    return JWTTenantMiddleware(inner)


def _make_jwt(payload: dict) -> str:
    """Create a signed JWT for testing."""
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


class TestJWTTenantMiddleware:

    def test_valid_jwt_sets_tenant(self, rf, middleware):
        """A valid JWT with org_id should switch tenant and set request.tenant."""
        from apps.core.models import Organization

        org_id = str(uuid.uuid4())
        token = _make_jwt({'org_id': org_id, 'sub': 'user1'})

        request = rf.get('/api/screening/predict')
        request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'

        mock_org = MagicMock()
        mock_org.id = org_id

        with patch('apps.core.models.Organization') as MockOrg, \
             patch('apps.billing.middleware.connection') as mock_conn:
            MockOrg.DoesNotExist = Organization.DoesNotExist
            MockOrg.objects.get.return_value = mock_org

            result = middleware(request)

        assert result == 'ok'
        assert request.tenant == mock_org
        mock_conn.set_tenant.assert_called_once_with(mock_org)

    def test_missing_auth_header_passes_through(self, rf, middleware):
        """Requests without Authorization header should pass through untouched."""
        request = rf.get('/api/screening/predict')
        # No Authorization header set

        result = middleware(request)

        assert result == 'ok'
        assert not hasattr(request, 'tenant')

    def test_non_bearer_auth_passes_through(self, rf, middleware):
        """Non-Bearer auth (e.g. Basic) should be ignored."""
        request = rf.get('/api/screening/predict')
        request.META['HTTP_AUTHORIZATION'] = 'Basic dXNlcjpwYXNz'

        result = middleware(request)

        assert result == 'ok'

    def test_expired_token_passes_through(self, rf, middleware):
        """Expired JWT should be silently ignored (no 500)."""
        import time
        token = _make_jwt({'org_id': 'some-org', 'sub': 'user1', 'exp': int(time.time()) - 3600})

        request = rf.get('/api/screening/predict')
        request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'

        result = middleware(request)

        assert result == 'ok'

    def test_invalid_token_passes_through(self, rf, middleware):
        """Garbage token should be silently ignored."""
        request = rf.get('/api/screening/predict')
        request.META['HTTP_AUTHORIZATION'] = 'Bearer not-a-valid-jwt'

        result = middleware(request)

        assert result == 'ok'

    def test_missing_org_id_passes_through(self, rf, middleware):
        """JWT without org_id claim should pass through without setting tenant."""
        token = _make_jwt({'sub': 'user1'})

        request = rf.get('/api/screening/predict')
        request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'

        with patch('apps.core.models.Organization') as MockOrg:
            result = middleware(request)

        assert result == 'ok'
        MockOrg.objects.get.assert_not_called()

    def test_nonexistent_org_passes_through(self, rf, middleware):
        """JWT with org_id that doesn't exist in DB should pass through."""
        from apps.core.models import Organization

        org_id = str(uuid.uuid4())
        token = _make_jwt({'org_id': org_id, 'sub': 'user1'})

        request = rf.get('/api/screening/predict')
        request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'

        with patch('apps.core.models.Organization') as MockOrg:
            MockOrg.DoesNotExist = Organization.DoesNotExist
            MockOrg.objects.get.side_effect = Organization.DoesNotExist

            result = middleware(request)

        assert result == 'ok'

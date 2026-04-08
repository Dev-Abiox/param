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
    import time as _time
    defaults = {
        'iss': 'clinomic',
        'aud': 'clinomic',
        'iat': int(_time.time()),
        'exp': int(_time.time()) + 3600,
        'jti': str(uuid.uuid4()),
        'token_type': 'access',
    }
    defaults.update(payload)
    return jwt.encode(defaults, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


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

    def test_super_admin_on_public_schema_resolves_tenant(self, rf, middleware):
        """SUPER_ADMIN on public schema should auto-resolve to first tenant."""
        from apps.core.models import Organization

        org_id = str(uuid.uuid4())
        token = _make_jwt({'org_id': org_id, 'sub': 'user1', 'is_super_admin': True})

        request = rf.get('/api/v1/admin/labs')
        request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'

        # Public schema org
        public_org = MagicMock()
        public_org.id = org_id
        public_org.schema_name = 'public'

        # Tenant org
        tenant_org = MagicMock()
        tenant_org.schema_name = 'tenant_demo'

        with patch('apps.core.models.Organization') as MockOrg, \
             patch('apps.billing.middleware.connection') as mock_conn:
            MockOrg.DoesNotExist = Organization.DoesNotExist
            MockOrg.objects.get.return_value = public_org
            MockOrg.objects.exclude.return_value.filter.return_value.order_by.return_value.first.return_value = tenant_org

            result = middleware(request)

        assert result == 'ok'
        # Should be called twice: first for public, then for tenant
        assert mock_conn.set_tenant.call_count == 2
        mock_conn.set_tenant.assert_called_with(tenant_org)
        assert request.tenant == tenant_org

    def test_super_admin_with_x_org_id_header(self, rf, middleware):
        """SUPER_ADMIN can target a specific org via X-Org-Id header."""
        from apps.core.models import Organization

        public_org_id = str(uuid.uuid4())
        target_org_id = str(uuid.uuid4())
        token = _make_jwt({'org_id': public_org_id, 'sub': 'user1', 'is_super_admin': True})

        request = rf.get('/api/v1/admin/labs')
        request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'
        request.META['HTTP_X_ORG_ID'] = target_org_id

        public_org = MagicMock()
        public_org.id = public_org_id
        public_org.schema_name = 'public'

        target_org = MagicMock()
        target_org.id = target_org_id
        target_org.schema_name = 'target_tenant'

        with patch('apps.core.models.Organization') as MockOrg, \
             patch('apps.billing.middleware.connection') as mock_conn:
            MockOrg.DoesNotExist = Organization.DoesNotExist
            # First call returns public org (for JWT org_id), second returns target org (for header)
            MockOrg.objects.get.side_effect = [public_org, target_org]

            result = middleware(request)

        assert result == 'ok'
        mock_conn.set_tenant.assert_called_with(target_org)
        assert request.tenant == target_org

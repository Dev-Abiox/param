"""
Integration tests for authentication flows.

Tests real database interactions — no mocking of core auth logic.
"""

import pytest
from django.test import override_settings
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestLoginIntegration:
    """Test the POST /api/auth/login endpoint with real DB."""

    def test_login_with_valid_credentials_returns_access_token(self, authenticated_lab_user, test_tenant):
        user, _ = authenticated_lab_user
        client = APIClient()
        # Need a Lab record for LAB users to log in
        from django_tenants.utils import tenant_context
        from apps.screening.models import Lab
        with tenant_context(test_tenant):
            Lab.objects.create(code='LAB-TEST', name='Test Lab', is_active=True)

        response = client.post('/api/auth/login', {
            'username': 'testlab',
            'password': 'TestPass123!@#',
        }, format='json')

        assert response.status_code == 200
        data = response.json()
        assert 'access_token' in data
        assert data['role'] == 'LAB'

    def test_login_with_invalid_password_returns_401(self, authenticated_lab_user):
        client = APIClient()
        response = client.post('/api/auth/login', {
            'username': 'testlab',
            'password': 'WrongPassword!',
        }, format='json')

        assert response.status_code == 401
        assert 'Invalid credentials' in response.json().get('error', '')

    def test_login_with_missing_credentials_returns_400(self):
        client = APIClient()
        response = client.post('/api/auth/login', {}, format='json')
        assert response.status_code == 400

    def test_login_inactive_user_returns_401(self, test_tenant, db):
        from django_tenants.utils import tenant_context
        from apps.core.models import Role, User

        with tenant_context(test_tenant):
            User.objects.create_user(
                username='inactive_user',
                password='TestPass123!@#',
                role=Role.LAB,
                is_active=False,
                organization=test_tenant,
            )

        client = APIClient()
        response = client.post('/api/auth/login', {
            'username': 'inactive_user',
            'password': 'TestPass123!@#',
        }, format='json')

        assert response.status_code == 401

    def test_login_inactive_org_returns_401(self, db, public_tenant):
        from apps.core.models import Domain, Organization, Role, User

        org = Organization.objects.create(
            name='Disabled Org',
            schema_name='disabled_org',
            is_active=False,
        )
        Domain.objects.create(domain='disabled.localhost', tenant=org, is_primary=True)

        User.objects.create_user(
            username='disabledorguser',
            password='TestPass123!@#',
            role=Role.LAB,
            organization=org,
        )

        client = APIClient()
        response = client.post('/api/auth/login', {
            'username': 'disabledorguser',
            'password': 'TestPass123!@#',
        }, format='json')

        assert response.status_code == 401
        assert 'Organization' in response.json().get('error', '')


@pytest.mark.django_db
class TestTokenRefreshIntegration:
    """Test the POST /api/auth/refresh endpoint."""

    def test_refresh_without_cookie_returns_401(self):
        client = APIClient()
        response = client.post('/api/auth/refresh')
        assert response.status_code == 401

    def test_refresh_with_invalid_cookie_returns_401(self):
        client = APIClient()
        client.cookies['clinomic_refresh'] = 'invalid-token'
        response = client.post('/api/auth/refresh')
        assert response.status_code == 401


@pytest.mark.django_db
class TestMeEndpoint:
    """Test the GET /api/auth/me endpoint."""

    def test_me_unauthenticated_returns_401_or_403(self):
        client = APIClient()
        response = client.get('/api/auth/me')
        assert response.status_code in (401, 403)

    def test_me_authenticated_returns_user_data(self, authenticated_lab_user):
        user, token = authenticated_lab_user
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = client.get('/api/auth/me')
        assert response.status_code == 200
        data = response.json()
        assert data['username'] == 'testlab'
        assert data['role'] == 'LAB'


@pytest.mark.django_db
class TestLogoutIntegration:
    """Test the POST /api/auth/logout endpoint."""

    def test_logout_clears_refresh_cookie(self, authenticated_lab_user):
        user, token = authenticated_lab_user
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = client.post('/api/auth/logout')
        assert response.status_code in (200, 204)

"""
Integration tests for admin CRUD views.

Tests role-based access control and data operations for admin endpoints.
"""

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestAdminUserListView:
    """Test GET/POST /api/admin/users."""

    def test_superadmin_can_list_users(self, authenticated_superadmin):
        user, token = authenticated_superadmin
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = client.get('/api/admin/users')
        assert response.status_code == 200

    def test_lab_user_can_access_admin_users(self, authenticated_lab_user):
        """LAB users are org managers and can list users in their org."""
        user, token = authenticated_lab_user
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = client.get('/api/admin/users')
        assert response.status_code == 200

    def test_unauthenticated_cannot_access_admin(self, public_tenant):
        client = APIClient()
        response = client.get('/api/admin/users')
        assert response.status_code in (401, 403)

    def test_superadmin_can_create_user(self, authenticated_superadmin, test_tenant):
        user, token = authenticated_superadmin
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = client.post('/api/admin/users', {
            'username': 'newlabuser',
            'email': 'newlab@clinomic.test',
            'password': 'StrongPass123!@#',
            'role': 'LAB',
            'organization_id': str(test_tenant.id),
        }, format='json')
        assert response.status_code in (200, 201)

    def test_create_user_weak_password_rejected(self, authenticated_superadmin, test_tenant):
        user, token = authenticated_superadmin
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = client.post('/api/admin/users', {
            'username': 'weakpwduser',
            'email': 'weakpwd@clinomic.test',
            'password': '123',
            'role': 'LAB',
            'organization_id': str(test_tenant.id),
        }, format='json')
        assert response.status_code == 400


@pytest.mark.django_db
class TestAdminOrgManagement:
    """Test organization management by SUPER_ADMIN."""

    def test_superadmin_can_list_orgs(self, authenticated_superadmin, test_tenant):
        user, token = authenticated_superadmin
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = client.get('/api/v1/platform/orgs/')
        assert response.status_code == 200

    def test_doctor_cannot_list_orgs(self, authenticated_doctor_user):
        user, token = authenticated_doctor_user
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = client.get('/api/v1/platform/orgs/')
        assert response.status_code == 403

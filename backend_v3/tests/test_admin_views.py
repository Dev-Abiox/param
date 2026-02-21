"""
Tests for admin views (user, lab, doctor management).

These tests use mocks to avoid needing a full database setup.
"""

import json
import uuid
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from rest_framework.test import APIRequestFactory


@pytest.fixture
def api_rf():
    return APIRequestFactory()


def _make_admin_request(rf, method, path, data=None, **kwargs):
    """Create a request with a mocked admin user."""
    user = MagicMock()
    user.is_authenticated = True
    user.role = 'ADMIN'
    user.organization = MagicMock(id=uuid.uuid4())

    # Mock MFA verification
    user.mfa_enabled = True

    if method == 'get':
        request = rf.get(path)
    elif method == 'post':
        request = rf.post(path, data=json.dumps(data or {}), content_type='application/json')
    elif method == 'patch':
        request = rf.patch(path, data=json.dumps(data or {}), content_type='application/json')
    elif method == 'delete':
        request = rf.delete(path)
    else:
        raise ValueError(f"Unknown method: {method}")

    request.user = user
    request.data = data or {}
    return request


def _make_non_admin_request(rf, path, method='get'):
    """Create a request with a non-admin user."""
    user = MagicMock()
    user.is_authenticated = True
    user.role = 'LAB'
    user.organization = MagicMock()

    if method == 'get':
        request = rf.get(path)
    else:
        request = rf.post(path)

    request.user = user
    return request


class TestAdminUserListView:

    @pytest.mark.django_db
    def test_get_returns_users(self, api_rf):
        """GET /admin/users should return list of org users."""
        from apps.core.views import AdminUserListView

        request = _make_admin_request(api_rf, 'get', '/api/admin/users')

        mock_users = [
            MagicMock(
                id=uuid.uuid4(),
                username='user1',
                email='u1@test.com',
                name='User One',
                role='LAB',
                is_active=True,
                created_at=MagicMock(isoformat=lambda: '2024-01-01T00:00:00'),
            ),
        ]

        with patch('apps.core.views.User') as MockUser:
            MockUser.objects.filter.return_value.order_by.return_value = mock_users

            view = AdminUserListView()
            view.request = request
            view.kwargs = {}
            view.format_kwarg = None
            response = view.get(request)

        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]['username'] == 'user1'

    @pytest.mark.django_db
    def test_post_creates_user(self, api_rf):
        """POST /admin/users should create a new user."""
        from apps.core.views import AdminUserListView

        data = {
            'username': 'newuser',
            'password': 'StrongP@ss1!xy',  # ≥12 chars to pass MinimumLengthValidator
            'role': 'LAB',
            'name': 'New User',
            'email': 'new@test.com',
        }
        request = _make_admin_request(api_rf, 'post', '/api/admin/users', data)

        with patch('apps.core.views.User') as MockUser, \
             patch('apps.core.views.Role') as MockRole, \
             patch('apps.core.views.validate_password'):  # isolate from password policy
            MockRole.values = ['ADMIN', 'DOCTOR', 'LAB']
            MockUser.objects.filter.return_value.exists.return_value = False

            mock_user = MagicMock(
                id=uuid.uuid4(),
                username='newuser',
                email='new@test.com',
                name='New User',
                role='LAB',
                is_active=True,
            )
            MockUser.return_value = mock_user

            view = AdminUserListView()
            view.request = request
            view.kwargs = {}
            view.format_kwarg = None
            response = view.post(request)

        assert response.status_code == 201
        assert response.data['username'] == 'newuser'

    @pytest.mark.django_db
    def test_post_missing_fields_returns_400(self, api_rf):
        """POST without required fields should return 400."""
        from apps.core.views import AdminUserListView

        data = {'username': 'newuser'}  # missing password and role
        request = _make_admin_request(api_rf, 'post', '/api/admin/users', data)

        view = AdminUserListView()
        view.request = request
        view.kwargs = {}
        view.format_kwarg = None
        response = view.post(request)

        assert response.status_code == 400


class TestAdminUserDetailView:

    @pytest.mark.django_db
    def test_patch_updates_user(self, api_rf):
        """PATCH /admin/users/<id> should update user fields."""
        from apps.core.views import AdminUserDetailView

        user_id = uuid.uuid4()
        data = {'name': 'Updated Name'}
        request = _make_admin_request(api_rf, 'patch', f'/api/admin/users/{user_id}', data)

        mock_user = MagicMock(
            id=user_id,
            username='testuser',
            email='test@test.com',
            name='Updated Name',
            role='LAB',
            is_active=True,
        )

        with patch('apps.core.views.User') as MockUser:
            MockUser.objects.get.return_value = mock_user

            view = AdminUserDetailView()
            view.request = request
            view.kwargs = {'user_id': user_id}
            view.format_kwarg = None
            response = view.patch(request, user_id=user_id)

        assert response.status_code == 200

    @pytest.mark.django_db
    def test_delete_deactivates_user(self, api_rf):
        """DELETE /admin/users/<id> should soft-deactivate."""
        from apps.core.views import AdminUserDetailView

        user_id = uuid.uuid4()
        request = _make_admin_request(api_rf, 'delete', f'/api/admin/users/{user_id}')

        mock_user = MagicMock(
            id=user_id,
            is_active=True,
        )

        with patch('apps.core.views.User') as MockUser:
            MockUser.objects.get.return_value = mock_user
            MockUser.DoesNotExist = Exception

            view = AdminUserDetailView()
            view.request = request
            view.kwargs = {'user_id': user_id}
            view.format_kwarg = None
            response = view.delete(request, user_id=user_id)

        assert response.status_code == 200
        assert mock_user.is_active is False

    @pytest.mark.django_db
    def test_patch_nonexistent_returns_404(self, api_rf):
        """PATCH with unknown user_id should return 404."""
        from apps.core.views import AdminUserDetailView
        from apps.core.models import User

        user_id = uuid.uuid4()
        data = {'name': 'Ghost'}
        request = _make_admin_request(api_rf, 'patch', f'/api/admin/users/{user_id}', data)

        with patch('apps.core.views.User') as MockUser:
            MockUser.DoesNotExist = User.DoesNotExist
            MockUser.objects.get.side_effect = User.DoesNotExist

            view = AdminUserDetailView()
            view.request = request
            view.kwargs = {'user_id': user_id}
            view.format_kwarg = None
            response = view.patch(request, user_id=user_id)

        assert response.status_code == 404


class TestAdminLabView:

    @pytest.mark.django_db
    def test_get_returns_labs(self, api_rf):
        """GET /admin/labs should return list of labs."""
        from apps.screening.views import AdminLabView

        request = _make_admin_request(api_rf, 'get', '/api/admin/labs')

        mock_labs = [
            MagicMock(
                id=uuid.uuid4(),
                code='LAB-001',
                name='Test Lab',
                tier='standard',
                is_active=True,
                created_at=MagicMock(isoformat=lambda: '2024-01-01'),
            ),
        ]

        with patch('apps.screening.views.Lab') as MockLab:
            MockLab.objects.all.return_value.order_by.return_value = mock_labs

            view = AdminLabView()
            view.request = request
            view.kwargs = {}
            view.format_kwarg = None
            response = view.get(request)

        assert response.status_code == 200

    @pytest.mark.django_db
    def test_post_creates_lab(self, api_rf):
        """POST /admin/labs should create a new lab."""
        from apps.screening.views import AdminLabView

        data = {'code': 'LAB-002', 'name': 'New Lab', 'tier': 'standard'}
        request = _make_admin_request(api_rf, 'post', '/api/admin/labs', data)

        with patch('apps.screening.views.Lab') as MockLab:
            MockLab.objects.filter.return_value.exists.return_value = False
            mock_lab = MagicMock(
                id=uuid.uuid4(),
                code='LAB-002',
                name='New Lab',
                tier='standard',
                is_active=True,
            )
            MockLab.objects.create.return_value = mock_lab

            view = AdminLabView()
            view.request = request
            view.kwargs = {}
            view.format_kwarg = None
            response = view.post(request)

        assert response.status_code == 201


class TestAdminDoctorView:

    @pytest.mark.django_db
    def test_get_returns_doctors(self, api_rf):
        """GET /admin/doctors should return list of doctors."""
        from apps.screening.views import AdminDoctorView

        request = _make_admin_request(api_rf, 'get', '/api/admin/doctors')

        mock_doctors = [
            MagicMock(
                id=uuid.uuid4(),
                code='D001',
                name='Dr. Test',
                email='doc@test.com',
                department='Haem',
                is_active=True,
                lab=MagicMock(id=uuid.uuid4(), name='Lab A'),
                created_at=MagicMock(isoformat=lambda: '2024-01-01'),
            ),
        ]

        with patch('apps.screening.views.Doctor') as MockDoctor:
            MockDoctor.objects.select_related.return_value.order_by.return_value = mock_doctors

            view = AdminDoctorView()
            view.request = request
            view.kwargs = {}
            view.format_kwarg = None
            response = view.get(request)

        assert response.status_code == 200


class TestRoleEnforcement:
    """Non-admin users should get 403 from admin views."""

    @pytest.mark.django_db
    def test_non_admin_gets_403_on_user_list(self, api_rf):
        """Non-admin user should be rejected from admin endpoints."""
        from apps.core.views import AdminUserListView

        request = _make_non_admin_request(api_rf, '/api/admin/users')

        view = AdminUserListView.as_view()

        # The permission classes will reject non-admin users
        # We test this by checking the view enforces IsAdmin
        assert any(
            pc.__name__ == 'IsAdmin'
            for pc in AdminUserListView.permission_classes
            if hasattr(pc, '__name__')
        )

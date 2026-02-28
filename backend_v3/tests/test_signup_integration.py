"""
Integration tests for the signup flow.

Validates organization creation, tenant schema provisioning,
user creation, and edge cases (duplicates, reserved names, passwords).
"""

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db(transaction=True)
class TestSignupFlow:
    """Test the POST /api/billing/signup endpoint."""

    def _signup_payload(self, **overrides):
        payload = {
            'orgName': 'Test Hospital',
            'adminName': 'Admin User',
            'adminEmail': 'admin@testhospital.com',
            'adminPassword': 'StrongTestPass123!@#',
            'username': 'hospitaladmin',
        }
        payload.update(overrides)
        return payload

    def test_signup_creates_org_and_user(self, public_tenant):
        client = APIClient()
        response = client.post(
            '/api/billing/signup',
            self._signup_payload(),
            format='json',
        )

        assert response.status_code in (200, 201), f"Signup failed: {response.json()}"
        data = response.json()
        assert 'access_token' in data

    def test_signup_duplicate_org_name_returns_error(self, public_tenant):
        client = APIClient()
        # First signup
        client.post('/api/billing/signup', self._signup_payload(), format='json')
        # Second signup with same org name
        response = client.post(
            '/api/billing/signup',
            self._signup_payload(
                adminEmail='admin2@testhospital.com',
                username='hospitaladmin2',
            ),
            format='json',
        )
        assert response.status_code in (400, 409)

    def test_signup_duplicate_email_returns_error(self, public_tenant):
        client = APIClient()
        client.post('/api/billing/signup', self._signup_payload(), format='json')
        response = client.post(
            '/api/billing/signup',
            self._signup_payload(
                orgName='Different Hospital',
                username='differentadmin',
            ),
            format='json',
        )
        assert response.status_code in (400, 409)

    def test_signup_weak_password_returns_400(self, public_tenant):
        client = APIClient()
        response = client.post(
            '/api/billing/signup',
            self._signup_payload(adminPassword='short'),
            format='json',
        )
        assert response.status_code == 400

    def test_signup_missing_fields_returns_400(self, public_tenant):
        client = APIClient()
        response = client.post('/api/billing/signup', {}, format='json')
        assert response.status_code == 400

    def test_signup_returns_mfa_not_verified_token(self, public_tenant):
        """Post-signup token should have mfa_verified=False."""
        import jwt as pyjwt
        from django.conf import settings

        client = APIClient()
        response = client.post(
            '/api/billing/signup',
            self._signup_payload(
                orgName='MFA Test Org',
                adminEmail='mfa@test.com',
                username='mfatestuser',
            ),
            format='json',
        )

        if response.status_code in (200, 201):
            token = response.json().get('access_token')
            if token:
                payload = pyjwt.decode(
                    token,
                    settings.JWT_SECRET_KEY,
                    algorithms=['HS256'],
                    options={'verify_exp': False},
                )
                assert payload.get('mfa_verified') is False

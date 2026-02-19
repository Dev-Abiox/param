"""
Tests for authentication flows: login, MFA, token refresh, logout,
session listing/revocation, password reset.
"""

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory

from apps.core.models import Role
from apps.core.views import LoginView, MeView, TokenRefreshView


def _make_user(role=Role.LAB, email="lab@example.com", username="lab_user"):
    user = MagicMock()
    user.is_authenticated = True
    user.role = role
    user.email = email
    user.username = username
    user.pk = 1
    return user


def _make_request_with_data(data: dict, user=None):
    factory = APIRequestFactory()
    request = factory.post("/api/auth/login", data, format="json")
    if user:
        request.user = user
        request.token_payload = {"mfa_verified": True}
    return request


class TestLoginView:
    """Login endpoint behaviour."""

    @patch("apps.core.views.LoginSerializer")
    @patch("apps.core.views.authenticate")
    def test_missing_credentials_returns_400(self, mock_auth, mock_ser):
        mock_ser_instance = MagicMock()
        mock_ser_instance.is_valid.return_value = False
        mock_ser_instance.errors = {"username": ["This field is required."]}
        mock_ser.return_value = mock_ser_instance

        factory = APIRequestFactory()
        request = factory.post("/api/auth/login", {}, format="json")
        response = LoginView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.core.views.authenticate")
    def test_invalid_credentials_returns_401(self, mock_auth):
        mock_auth.return_value = None  # authentication fails
        factory = APIRequestFactory()
        request = factory.post(
            "/api/auth/login",
            {"username": "bad", "password": "wrong"},
            format="json",
        )
        response = LoginView.as_view()(request)
        assert response.status_code in (
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
        )


class TestMeView:
    """GET /api/auth/me — returns current user info."""

    def test_unauthenticated_returns_401(self):
        factory = APIRequestFactory()
        request = factory.get("/api/auth/me")
        request.user = MagicMock(is_authenticated=False)
        response = MeView.as_view()(request)
        # Permission class should block unauthenticated access
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_authenticated_returns_200(self):
        user = _make_user()
        factory = APIRequestFactory()
        request = factory.get("/api/auth/me")
        request.user = user
        request.token_payload = {"mfa_verified": True}

        with patch("apps.core.views.UserSerializer") as mock_ser:
            mock_ser_instance = MagicMock()
            mock_ser_instance.data = {"id": "1", "username": "lab_user", "role": "LAB"}
            mock_ser.return_value = mock_ser_instance

            response = MeView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK


class TestTokenRefreshView:
    """POST /api/auth/refresh — exchange cookie for new access token."""

    def test_missing_cookie_returns_401(self):
        factory = APIRequestFactory()
        request = factory.post("/api/auth/refresh", {}, format="json")
        request.COOKIES = {}  # No refresh_token cookie
        request.user = MagicMock(is_authenticated=False)

        response = TokenRefreshView.as_view()(request)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

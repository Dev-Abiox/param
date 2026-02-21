"""
Tests for JWT authentication and API key authentication backends.
"""

import hashlib
import time
import uuid
from unittest.mock import MagicMock, patch

import jwt
import pytest
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory


def _make_token(payload: dict) -> str:
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _access_payload(**overrides):
    now = int(time.time())
    base = {
        'sub': str(uuid.uuid4()),
        'username': 'testuser',
        'role': 'LAB',
        'org_id': str(uuid.uuid4()),
        'is_super_admin': False,
        'mfa_verified': True,
        'token_type': 'access',
        'jti': str(uuid.uuid4()),
        'iat': now,
        'exp': now + 3600,
    }
    base.update(overrides)
    return base


# ── JWTAuthentication ────────────────────────────────────────────────────────

class TestJWTAuthentication:

    def test_valid_token_returns_user(self):
        from apps.core.authentication import JWTAuthentication

        payload = _access_payload()
        token = _make_token(payload)
        factory = APIRequestFactory()
        request = factory.get('/api/test')
        request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'

        mock_user = MagicMock()
        mock_user.is_active = True

        auth = JWTAuthentication()
        with patch('apps.core.authentication.User') as MockUser:
            MockUser.objects.get.return_value = mock_user
            result = auth.authenticate(request)

        assert result is not None
        user, token_payload = result
        assert user == mock_user
        assert token_payload['sub'] == payload['sub']

    def test_no_auth_header_returns_none(self):
        from apps.core.authentication import JWTAuthentication

        factory = APIRequestFactory()
        request = factory.get('/api/test')

        auth = JWTAuthentication()
        result = auth.authenticate(request)
        assert result is None

    def test_non_bearer_header_returns_none(self):
        from apps.core.authentication import JWTAuthentication

        factory = APIRequestFactory()
        request = factory.get('/api/test')
        request.META['HTTP_AUTHORIZATION'] = 'Basic dXNlcjpwYXNz'

        auth = JWTAuthentication()
        result = auth.authenticate(request)
        assert result is None

    def test_expired_token_raises(self):
        from apps.core.authentication import JWTAuthentication

        payload = _access_payload(exp=int(time.time()) - 3600)
        token = _make_token(payload)
        factory = APIRequestFactory()
        request = factory.get('/api/test')
        request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'

        auth = JWTAuthentication()
        with pytest.raises(AuthenticationFailed, match='expired'):
            auth.authenticate(request)

    def test_invalid_token_raises(self):
        from apps.core.authentication import JWTAuthentication

        factory = APIRequestFactory()
        request = factory.get('/api/test')
        request.META['HTTP_AUTHORIZATION'] = 'Bearer not-a-valid-jwt'

        auth = JWTAuthentication()
        with pytest.raises(AuthenticationFailed, match='Invalid token'):
            auth.authenticate(request)

    def test_user_not_found_raises(self):
        from apps.core.authentication import JWTAuthentication
        from apps.core.models import User

        payload = _access_payload()
        token = _make_token(payload)
        factory = APIRequestFactory()
        request = factory.get('/api/test')
        request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'

        auth = JWTAuthentication()
        with patch('apps.core.authentication.User') as MockUser:
            MockUser.DoesNotExist = User.DoesNotExist
            MockUser.objects.get.side_effect = User.DoesNotExist
            with pytest.raises(AuthenticationFailed, match='User not found'):
                auth.authenticate(request)

    def test_inactive_user_raises(self):
        from apps.core.authentication import JWTAuthentication

        payload = _access_payload()
        token = _make_token(payload)
        factory = APIRequestFactory()
        request = factory.get('/api/test')
        request.META['HTTP_AUTHORIZATION'] = f'Bearer {token}'

        mock_user = MagicMock()
        mock_user.is_active = False

        auth = JWTAuthentication()
        with patch('apps.core.authentication.User') as MockUser:
            MockUser.objects.get.return_value = mock_user
            with pytest.raises(AuthenticationFailed, match='inactive'):
                auth.authenticate(request)


# ── Token creation & decoding ────────────────────────────────────────────────

class TestTokenFunctions:

    def test_create_access_token_roundtrip(self):
        from apps.core.authentication import create_access_token, decode_token

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.username = 'testuser'
        mock_user.role = 'LAB'
        mock_user.organization_id = uuid.uuid4()
        mock_user.is_superuser = False

        token = create_access_token(mock_user, mfa_verified=True)
        payload = decode_token(token, token_type='access')

        assert payload['sub'] == str(mock_user.id)
        assert payload['username'] == 'testuser'
        assert payload['role'] == 'LAB'
        assert payload['mfa_verified'] is True
        assert payload['token_type'] == 'access'

    def test_decode_wrong_type_raises(self):
        from apps.core.authentication import create_access_token, decode_token

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.username = 'testuser'
        mock_user.role = 'LAB'
        mock_user.organization_id = uuid.uuid4()
        mock_user.is_superuser = False

        token = create_access_token(mock_user)
        with pytest.raises(jwt.InvalidTokenError, match='Expected refresh.*got access'):
            decode_token(token, token_type='refresh')

    def test_create_mfa_pending_token(self):
        from apps.core.authentication import create_mfa_pending_token, decode_token

        mock_user = MagicMock()
        mock_user.id = uuid.uuid4()
        mock_user.username = 'mfa_user'
        mock_user.role = 'DOCTOR'

        token = create_mfa_pending_token(mock_user)
        payload = decode_token(token, token_type='mfa_pending')

        assert payload['sub'] == str(mock_user.id)
        assert payload['token_type'] == 'mfa_pending'


# ── APIKeyAuthentication ────────────────────────────────────────────────────

class TestAPIKeyAuthentication:

    def test_no_header_returns_none(self):
        from apps.core.authentication import APIKeyAuthentication

        factory = APIRequestFactory()
        request = factory.get('/api/test')

        auth = APIKeyAuthentication()
        result = auth.authenticate(request)
        assert result is None

    def test_valid_key_returns_user(self):
        from apps.core.authentication import APIKeyAuthentication

        raw_key = 'clk_test_abc123xyz'
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        mock_user = MagicMock()
        mock_user.is_active = True
        mock_api_key = MagicMock()
        mock_api_key.is_active = True
        mock_api_key.created_by = mock_user
        mock_api_key.pk = uuid.uuid4()

        factory = APIRequestFactory()
        request = factory.get('/api/test')
        request.META['HTTP_X_API_KEY'] = raw_key

        auth = APIKeyAuthentication()
        with patch('apps.billing.models.APIKey') as MockAPIKey:
            MockAPIKey.DoesNotExist = Exception
            MockAPIKey.objects.select_related.return_value.get.return_value = mock_api_key
            MockAPIKey.objects.filter.return_value.update.return_value = 1

            result = auth.authenticate(request)

        assert result is not None
        user, key = result
        assert user == mock_user
        assert key == mock_api_key

    def test_invalid_key_raises(self):
        from apps.core.authentication import APIKeyAuthentication
        from apps.billing.models import APIKey

        factory = APIRequestFactory()
        request = factory.get('/api/test')
        request.META['HTTP_X_API_KEY'] = 'bad_key'

        auth = APIKeyAuthentication()
        with patch('apps.billing.models.APIKey') as MockAPIKey:
            MockAPIKey.DoesNotExist = APIKey.DoesNotExist
            MockAPIKey.objects.select_related.return_value.get.side_effect = APIKey.DoesNotExist

            with pytest.raises(AuthenticationFailed, match='Invalid API key'):
                auth.authenticate(request)

    def test_revoked_key_raises(self):
        from apps.core.authentication import APIKeyAuthentication

        mock_api_key = MagicMock()
        mock_api_key.is_active = False

        factory = APIRequestFactory()
        request = factory.get('/api/test')
        request.META['HTTP_X_API_KEY'] = 'some_key'

        auth = APIKeyAuthentication()
        with patch('apps.billing.models.APIKey') as MockAPIKey:
            MockAPIKey.DoesNotExist = Exception
            MockAPIKey.objects.select_related.return_value.get.return_value = mock_api_key

            with pytest.raises(AuthenticationFailed, match='revoked'):
                auth.authenticate(request)

    def test_inactive_owner_raises(self):
        from apps.core.authentication import APIKeyAuthentication

        mock_user = MagicMock()
        mock_user.is_active = False
        mock_api_key = MagicMock()
        mock_api_key.is_active = True
        mock_api_key.created_by = mock_user

        factory = APIRequestFactory()
        request = factory.get('/api/test')
        request.META['HTTP_X_API_KEY'] = 'some_key'

        auth = APIKeyAuthentication()
        with patch('apps.billing.models.APIKey') as MockAPIKey:
            MockAPIKey.DoesNotExist = Exception
            MockAPIKey.objects.select_related.return_value.get.return_value = mock_api_key

            with pytest.raises(AuthenticationFailed, match='inactive'):
                auth.authenticate(request)

    def test_authenticate_header(self):
        from apps.core.authentication import APIKeyAuthentication

        auth = APIKeyAuthentication()
        assert auth.authenticate_header(None) == 'X-API-Key'

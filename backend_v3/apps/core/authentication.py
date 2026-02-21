"""
JWT Authentication for Clinomic Platform.

Provides stateless JWT authentication with refresh token rotation,
and API key authentication for programmatic access.
"""

import hashlib
import uuid
from datetime import datetime, timezone

import jwt
from django.conf import settings
from django.utils import timezone as dj_timezone
from rest_framework import authentication, exceptions

from .models import RefreshToken, User


class JWTAuthentication(authentication.BaseAuthentication):
    """
    Custom JWT authentication class for DRF.
    """
    keyword = 'Bearer'

    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')

        if not auth_header.startswith(f'{self.keyword} '):
            return None

        token = auth_header[len(self.keyword) + 1:]

        try:
            payload = decode_token(token, token_type='access')
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed('Token has expired')
        except jwt.InvalidTokenError as e:
            raise exceptions.AuthenticationFailed(f'Invalid token: {str(e)}')

        try:
            user = User.objects.get(id=payload['sub'])
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed('User not found')

        if not user.is_active:
            raise exceptions.AuthenticationFailed('User is inactive')

        # Attach token payload to request for later use
        request.token_payload = payload

        return (user, payload)


def create_access_token(user: User, mfa_verified: bool = False) -> str:
    """
    Create a JWT access token for a user.
    """
    now = datetime.now(timezone.utc)
    payload = {
        'sub': str(user.id),
        'username': user.username,
        'role': user.role,
        'org_id': str(user.organization_id) if user.organization_id else None,
        'is_super_admin': user.is_superuser,
        'mfa_verified': mfa_verified,
        'token_type': 'access',
        'jti': str(uuid.uuid4()),
        'iat': int(now.timestamp()),
        'exp': int((now + settings.JWT_ACCESS_TOKEN_LIFETIME).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user: User) -> tuple[str, RefreshToken]:
    """
    Create a JWT refresh token and store its hash.

    Returns:
        tuple: (token_string, RefreshToken model instance)
    """
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())

    payload = {
        'sub': str(user.id),
        'token_type': 'refresh',
        'jti': jti,
        'iat': int(now.timestamp()),
        'exp': int((now + settings.JWT_REFRESH_TOKEN_LIFETIME).timestamp()),
    }

    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    # Store refresh token
    refresh_token = RefreshToken.objects.create(
        user=user,
        token_hash=token_hash,
        expires_at=now + settings.JWT_REFRESH_TOKEN_LIFETIME,
    )

    return token, refresh_token


def create_mfa_pending_token(user: User) -> str:
    """
    Create a short-lived token for MFA verification step.
    """
    from datetime import timedelta
    now = datetime.now(timezone.utc)

    payload = {
        'sub': str(user.id),
        'username': user.username,
        'role': user.role,
        'token_type': 'mfa_pending',
        'jti': str(uuid.uuid4()),
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(minutes=5)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, token_type: str = 'access') -> dict:
    """
    Decode and validate a JWT token.

    Args:
        token: The JWT token string
        token_type: Expected token type ('access', 'refresh', 'mfa_pending')

    Returns:
        Decoded token payload

    Raises:
        jwt.InvalidTokenError: If token is invalid or wrong type
    """
    payload = jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM]
    )

    # Validate token type
    actual_type = payload.get('token_type', 'access')
    if actual_type != token_type:
        raise jwt.InvalidTokenError(f'Expected {token_type} token, got {actual_type}')

    return payload


def refresh_tokens(refresh_token_str: str) -> tuple[str, str]:
    """
    Rotate refresh token and issue new access token.

    Args:
        refresh_token_str: The current refresh token

    Returns:
        tuple: (new_access_token, new_refresh_token)

    Raises:
        exceptions.AuthenticationFailed: If refresh token is invalid or revoked
    """
    # Decode and validate
    try:
        payload = decode_token(refresh_token_str, token_type='refresh')
    except jwt.ExpiredSignatureError:
        raise exceptions.AuthenticationFailed('Refresh token has expired')
    except jwt.InvalidTokenError as e:
        raise exceptions.AuthenticationFailed(f'Invalid refresh token: {str(e)}')

    # Find stored token
    token_hash = hashlib.sha256(refresh_token_str.encode()).hexdigest()

    try:
        stored_token = RefreshToken.objects.get(token_hash=token_hash)
    except RefreshToken.DoesNotExist:
        raise exceptions.AuthenticationFailed('Refresh token not found')

    if stored_token.is_revoked:
        # Possible token reuse attack - revoke all user tokens
        RefreshToken.objects.filter(user=stored_token.user).update(is_revoked=True)
        raise exceptions.AuthenticationFailed('Token has been revoked')

    # Revoke old token
    stored_token.is_revoked = True
    stored_token.save()

    # Get user and create new tokens
    user = stored_token.user

    new_access_token = create_access_token(user, mfa_verified=True)
    new_refresh_token, _ = create_refresh_token(user)

    return new_access_token, new_refresh_token


def revoke_refresh_token(refresh_token_str: str) -> bool:
    """
    Revoke a refresh token (logout).
    """
    token_hash = hashlib.sha256(refresh_token_str.encode()).hexdigest()

    updated = RefreshToken.objects.filter(
        token_hash=token_hash,
        is_revoked=False
    ).update(is_revoked=True)

    return updated > 0


# ── API Key Authentication ──────────────────────────────────────────────────────

class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Custom DRF authentication class for API key access.

    Reads the raw key from the ``X-API-Key`` request header, computes its
    SHA-256 digest, looks it up in ``billing.APIKey``, and — if valid —
    sets:

    * ``request.user``    → the ``User`` who created the key
    * ``request.api_key`` → the ``APIKey`` model instance (for scope / rate-limit checks)

    The ``last_used_at`` timestamp is updated on every successful authentication
    for billing and auditing purposes.

    This authenticator returns ``None`` (not an error) when no ``X-API-Key``
    header is present, so that other authenticators (e.g. JWTAuthentication)
    can still handle the request.
    """

    HEADER = 'HTTP_X_API_KEY'

    def authenticate(self, request):
        raw_key = request.META.get(self.HEADER, '').strip()
        if not raw_key:
            return None  # Let other authenticators run

        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        # Import here to avoid circular imports at module load time
        from apps.billing.models import APIKey

        try:
            api_key = (
                APIKey.objects
                .select_related('created_by', 'organization')
                .get(key_hash=key_hash)
            )
        except APIKey.DoesNotExist:
            raise exceptions.AuthenticationFailed('Invalid API key.')

        if not api_key.is_active:
            raise exceptions.AuthenticationFailed('API key has been revoked.')

        if api_key.created_by is None or not api_key.created_by.is_active:
            raise exceptions.AuthenticationFailed('API key owner account is inactive.')

        # Track last usage (fire-and-forget; no transaction needed here)
        APIKey.objects.filter(pk=api_key.pk).update(last_used_at=dj_timezone.now())
        api_key.last_used_at = dj_timezone.now()  # Update in-memory too

        # Attach the key to the request so views / throttles can inspect it
        request.api_key = api_key

        return (api_key.created_by, api_key)

    def authenticate_header(self, request):
        return 'X-API-Key'

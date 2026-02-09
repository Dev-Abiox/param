"""
JWT Authentication for Clinomic Platform.

Provides stateless JWT authentication with refresh token rotation.
"""

import hashlib
import uuid
from datetime import datetime, timezone

import jwt
from django.conf import settings
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

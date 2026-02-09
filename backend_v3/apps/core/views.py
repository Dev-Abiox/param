"""
Core API views for authentication, MFA, and health checks.
"""

import logging

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import connection
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .authentication import (
    create_access_token,
    create_mfa_pending_token,
    create_refresh_token,
    decode_token,
    refresh_tokens,
    revoke_refresh_token,
)
from .crypto import get_crypto_status
from .mfa import MFAManager
from .models import User
from .serializers import (
    LoginSerializer,
    LogoutSerializer,
    MFACodeSerializer,
    MFASetupSerializer,
    MFAStatusSerializer,
    MFAVerifySerializer,
    TokenRefreshSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)


class LoginRateThrottle(AnonRateThrottle):
    rate = '5/minute'


class LoginView(APIView):
    """
    User login endpoint.

    POST /api/auth/login
    """
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data['username']
        password = serializer.validated_data['password']
        mfa_code = serializer.validated_data.get('mfa_code')

        # Authenticate user
        user = authenticate(request, username=username, password=password)
        if not user:
            return Response(
                {'error': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_active:
            return Response(
                {'error': 'Account is disabled'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Check if MFA is required
        mfa_status = MFAManager.get_mfa_status(user)

        if mfa_status['enabled']:
            if not mfa_code:
                # Return MFA pending token
                pending_token = create_mfa_pending_token(user)
                return Response({
                    'mfa_required': True,
                    'mfa_pending_token': pending_token,
                    'id': str(user.id),
                    'name': user.name or user.username,
                    'role': user.role,
                })

            # Verify MFA code
            if not MFAManager.verify_code(user, mfa_code):
                return Response(
                    {'error': 'Invalid MFA code'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

        # Create tokens
        access_token = create_access_token(user, mfa_verified=mfa_status['enabled'])
        refresh_token, _ = create_refresh_token(user)

        return Response({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'id': str(user.id),
            'name': user.name or user.username,
            'role': user.role,
        })


class MFAVerifyView(APIView):
    """
    Complete MFA verification after login.

    POST /api/auth/mfa/verify
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = MFAVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        pending_token = serializer.validated_data['mfa_pending_token']
        mfa_code = serializer.validated_data['mfa_code']

        # Decode pending token
        try:
            payload = decode_token(pending_token, token_type='mfa_pending')
        except Exception as e:
            return Response(
                {'error': 'Invalid or expired MFA token'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Get user
        try:
            user = User.objects.get(id=payload['sub'])
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Verify MFA code
        if not MFAManager.verify_code(user, mfa_code):
            return Response(
                {'error': 'Invalid MFA code'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Create tokens
        access_token = create_access_token(user, mfa_verified=True)
        refresh_token, _ = create_refresh_token(user)

        return Response({
            'access_token': access_token,
            'refresh_token': refresh_token,
            'id': str(user.id),
            'name': user.name or user.username,
            'role': user.role,
        })


class TokenRefreshView(APIView):
    """
    Refresh access token using refresh token.

    POST /api/auth/refresh
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            access_token, new_refresh_token = refresh_tokens(
                serializer.validated_data['refresh_token']
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_401_UNAUTHORIZED
            )

        return Response({
            'access_token': access_token,
            'refresh_token': new_refresh_token,
        })


class LogoutView(APIView):
    """
    Logout and revoke refresh token.

    POST /api/auth/logout
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        revoke_refresh_token(serializer.validated_data['refresh_token'])

        return Response({'status': 'logged out'})


class MeView(APIView):
    """
    Get current user info.

    GET /api/auth/me
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class MFASetupView(APIView):
    """
    Initialize MFA setup.

    POST /api/mfa/setup
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MFASetupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = MFAManager.setup_mfa(
            request.user,
            email=serializer.validated_data.get('email')
        )

        return Response(result)


class MFAVerifySetupView(APIView):
    """
    Verify MFA setup with a code.

    POST /api/mfa/verify-setup
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MFACodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = MFAManager.verify_setup(
            request.user,
            serializer.validated_data['code']
        )

        if not result['success']:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        return Response(result)


class MFAStatusView(APIView):
    """
    Get MFA status for current user.

    GET /api/mfa/status
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        mfa_status = MFAManager.get_mfa_status(request.user)
        serializer = MFAStatusSerializer(mfa_status)
        return Response(serializer.data)


class MFADisableView(APIView):
    """
    Disable MFA.

    POST /api/mfa/disable
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MFACodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = MFAManager.disable_mfa(
            request.user,
            serializer.validated_data['code']
        )

        if not result['success']:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        return Response(result)


class MFABackupCodesView(APIView):
    """
    Regenerate MFA backup codes.

    POST /api/mfa/backup-codes/regenerate
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MFACodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = MFAManager.regenerate_backup_codes(
            request.user,
            serializer.validated_data['code']
        )

        if not result['success']:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        return Response(result)


class HealthLiveView(APIView):
    """
    Liveness probe.

    GET /api/health/live
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'status': 'live'})


class HealthReadyView(APIView):
    """
    Readiness probe - checks all dependencies.

    GET /api/health/ready
    """
    permission_classes = [AllowAny]

    def get(self, request):
        errors = []

        # Check database
        try:
            connection.ensure_connection()
            db_ok = True
        except Exception as e:
            db_ok = False
            errors.append(f'database: {str(e)}')

        # Check ML engine
        from apps.screening.ml_engine import get_ml_engine
        ml_engine = get_ml_engine()
        ml_status = ml_engine.get_status()
        if not ml_status['ready']:
            errors.append(f"ml_engine: {ml_status.get('error', 'not ready')}")

        # Check crypto
        crypto_status = get_crypto_status()

        if errors:
            return Response(
                {
                    'status': 'not ready',
                    'errors': errors,
                    'database': db_ok,
                    'ml_engine': ml_status,
                    'crypto': crypto_status,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        return Response({
            'status': 'ready',
            'database': db_ok,
            'ml_engine': ml_status,
            'crypto': crypto_status,
        })

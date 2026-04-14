"""
Core API views for authentication, MFA, and health checks.
"""

import hashlib
import logging
import secrets
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import connection
from django.http import JsonResponse
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
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
from .models import MFAMethod, Role, User
from .permissions import IsAdmin, IsMFAVerified, IsOrgManager
from .serializers import (
    LoginSerializer,
    MFACodeSerializer,
    MFAResendOTPSerializer,
    MFASetupSerializer,
    MFAStatusSerializer,
    MFAVerifySerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)

_REFRESH_COOKIE = 'refresh_token'


def _set_refresh_cookie(response, token: str) -> None:
    """Set the refresh token as an httpOnly cookie restricted to auth endpoints."""
    max_age = int(settings.JWT_REFRESH_TOKEN_LIFETIME.total_seconds())
    response.set_cookie(
        _REFRESH_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=not settings.DEBUG,   # False only in local dev
        samesite='Strict',
        path='/api/auth/',
    )


def _delete_refresh_cookie(response) -> None:
    response.delete_cookie(_REFRESH_COOKIE, path='/api/auth/')


_DEVICE_COOKIE = 'trusted_device'
_DEVICE_MAX_AGE = 30 * 24 * 3600  # 30 days


def _create_trusted_device(user, request):
    """Create a trusted device token and return it."""
    from .models import TrustedDevice
    from django.utils import timezone
    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    TrustedDevice.objects.create(
        user=user,
        token_hash=token_hash,
        user_agent=(request.META.get('HTTP_USER_AGENT', '') or '')[:500],
        ip_address=request.META.get('REMOTE_ADDR'),
        expires_at=timezone.now() + timedelta(days=30),
    )
    return raw_token


def _set_device_cookie(response, token: str) -> None:
    response.set_cookie(
        _DEVICE_COOKIE,
        token,
        max_age=_DEVICE_MAX_AGE,
        httponly=True,
        secure=not settings.DEBUG,
        samesite='Strict',
        path='/api/auth/',
    )


def _check_trusted_device(user, request) -> bool:
    """Return True if the request carries a valid trusted-device cookie.

    Bind the cookie to the source IP: if the token was issued from IP X,
    only honour it when the same IP presents it later. A stolen cookie
    replayed from a different network will drop back through normal MFA.
    """
    from .models import TrustedDevice
    from django.utils import timezone
    raw_token = request.COOKIES.get(_DEVICE_COOKIE)
    if not raw_token:
        return False
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    device = TrustedDevice.objects.filter(
        user=user,
        token_hash=token_hash,
        expires_at__gt=timezone.now(),
    ).first()
    if device is None:
        return False
    current_ip = request.META.get('REMOTE_ADDR')
    if device.ip_address and current_ip and device.ip_address != current_ip:
        return False
    return True


from .throttling import (
    LoginRateThrottle,
    MFAResendThrottle,
    MFATOTPThrottle,
    PasswordResetRateThrottle,
    RefreshTokenThrottle,
)


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

        identifier = serializer.validated_data['username']
        password = serializer.validated_data['password']
        mfa_code = serializer.validated_data.get('mfa_code')

        # Authenticate by username first, fall back to email lookup
        user = authenticate(request, username=identifier, password=password)
        if not user and '@' in identifier:
            try:
                email_user = User.objects.get(email__iexact=identifier)
                user = authenticate(request, username=email_user.username, password=password)
            except User.DoesNotExist:
                pass
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

        # Block login when the parent organization is deactivated
        if user.organization and not user.organization.is_active:
            return Response(
                {'error': 'Organization account is disabled'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Switch to the user's tenant schema so tenant-specific queries
        # (Lab, Doctor) resolve correctly. Login requests have no JWT yet,
        # so JWTTenantMiddleware cannot do this automatically.
        if user.organization and user.organization.schema_name != 'public':
            from django.db import connection as db_connection
            db_connection.set_tenant(user.organization)

        # Block LAB users only when labs exist but all are deactivated.
        # If no labs exist yet (pre-onboarding), allow login so they can set up.
        if user.role == Role.LAB:
            from apps.screening.models import Lab
            lab_qs = Lab.objects.all()
            if lab_qs.exists() and not lab_qs.filter(is_active=True).exists():
                return Response(
                    {'error': 'Lab account is inactive. Contact your administrator.'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

        # Block DOCTOR users only when a doctor record exists but is deactivated.
        # If no record exists yet the user was just created and should be allowed in.
        if user.role == Role.DOCTOR and user.email:
            from apps.screening.models import Doctor
            doctor_qs = Doctor.objects.filter(email=user.email)
            if doctor_qs.exists() and not doctor_qs.filter(is_active=True).exists():
                return Response(
                    {'error': 'Doctor account is inactive. Contact your administrator.'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

        # Check if MFA is required
        mfa_status = MFAManager.get_mfa_status(user)

        # C4: LAB, DOCTOR, and SUPER_ADMIN must have MFA set up before accessing features.
        # If they haven't configured MFA yet, issue a restricted token that only
        # allows the MFA-setup endpoints (mfa_verified=False blocks everything else).
        MFA_REQUIRED_ROLES = {Role.LAB, Role.DOCTOR, Role.SUPER_ADMIN}
        if user.role in MFA_REQUIRED_ROLES and not mfa_status['enabled']:
            restricted_token = create_access_token(user, mfa_verified=False)
            refresh_token, _ = create_refresh_token(user)
            resp = Response({
                'access_token': restricted_token,
                'mfaSetupRequired': True,
                'id': str(user.id),
                'name': user.name or user.username,
                'role': user.role,
            })
            _set_refresh_cookie(resp, refresh_token)
            return resp

        if mfa_status['enabled']:
            # Auto-migrate TOTP users to EMAIL on login
            if mfa_status['mfa_method'] != MFAMethod.EMAIL:
                MFAManager.migrate_totp_to_email(user)
                mfa_status['mfa_method'] = MFAMethod.EMAIL

            # Skip MFA if this device is trusted (remember-me cookie)
            if not mfa_code and _check_trusted_device(user, request):
                access_token = create_access_token(user, mfa_verified=True)
                refresh_token, _ = create_refresh_token(user, mfa_verified=True)
                response = Response({
                    'access_token': access_token,
                    'id': str(user.id),
                    'name': user.name or user.username,
                    'role': user.role,
                })
                _set_refresh_cookie(response, refresh_token)
                return response

            if not mfa_code:
                pending_token = create_mfa_pending_token(user)
                from .mfa import _mask_email
                otp_email = MFAManager.get_otp_email(user)
                code = MFAManager.generate_email_otp(user)
                MFAManager._send_otp_email(user, code, otp_email)

                resp_data = {
                    'mfa_required': True,
                    'mfa_pending_token': pending_token,
                    'mfa_method': MFAMethod.EMAIL,
                    'id': str(user.id),
                    'name': user.name or user.username,
                    'role': user.role,
                    'masked_email': _mask_email(otp_email),
                }

                return Response(resp_data)

            # Verify MFA code
            if not MFAManager.verify_code(user, mfa_code):
                return Response(
                    {'error': 'Invalid MFA code'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

        # Create tokens
        # mfa_verified=True: if we reach this line the user either passed TOTP
        # verification above (MFA enabled) or MFA is not set up — both cases
        # mean the user is fully authenticated.
        access_token = create_access_token(user, mfa_verified=True)
        refresh_token, _ = create_refresh_token(user, mfa_verified=True)

        response = Response({
            'access_token': access_token,
            'id': str(user.id),
            'name': user.name or user.username,
            'role': user.role,
        })
        _set_refresh_cookie(response, refresh_token)
        return response


class MFAVerifyView(APIView):
    """
    Complete MFA verification after login.

    POST /api/auth/mfa/verify
    Rate-limited to 5 attempts per 5 minutes per IP+user to prevent brute force.
    """
    permission_classes = [AllowAny]
    throttle_classes = [MFATOTPThrottle]

    def post(self, request):
        serializer = MFAVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        pending_token = serializer.validated_data['mfa_pending_token']
        mfa_code = serializer.validated_data['mfa_code']

        # Decode pending token
        try:
            payload = decode_token(pending_token, token_type='mfa_pending')
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, KeyError, ValueError) as e:
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

        # Create tokens — MFA was just verified, so mfa_verified=True
        access_token = create_access_token(user, mfa_verified=True)
        refresh_token, _ = create_refresh_token(user, mfa_verified=True)

        response = Response({
            'access_token': access_token,
            'id': str(user.id),
            'name': user.name or user.username,
            'role': user.role,
        })
        _set_refresh_cookie(response, refresh_token)

        # Set trusted-device cookie if requested
        remember_device = serializer.validated_data.get('remember_device', False)
        if remember_device:
            device_token = _create_trusted_device(user, request)
            _set_device_cookie(response, device_token)

        return response


class TokenRefreshView(APIView):
    """
    Refresh access token using the httpOnly refresh-token cookie.

    POST /api/auth/refresh
    No body required — the refresh token is read from the cookie set at login.
    """
    permission_classes = [AllowAny]
    throttle_classes = [RefreshTokenThrottle]

    def post(self, request):
        token = request.COOKIES.get(_REFRESH_COOKIE)
        if not token:
            return Response(
                {'error': 'No refresh token'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        try:
            access_token, new_refresh_token = refresh_tokens(token)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError):
            response = Response({'error': 'Invalid or expired refresh token'}, status=status.HTTP_401_UNAUTHORIZED)
            _delete_refresh_cookie(response)
            return response

        response = Response({'access_token': access_token})
        _set_refresh_cookie(response, new_refresh_token)
        return response


class LogoutView(APIView):
    """
    Logout and revoke the httpOnly refresh-token cookie.

    POST /api/auth/logout
    No body required.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.COOKIES.get(_REFRESH_COOKIE)
        if token:
            revoke_refresh_token(token)

        response = Response({'status': 'logged out'})
        _delete_refresh_cookie(response)
        return response


class MeView(APIView):
    """
    Get current user info.

    GET /api/auth/me

    Only requires authentication (no MFA gate) so the frontend can always
    fetch the user profile — including during the MFA-setup flow — and
    decide what UI to render.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        data = serializer.data
        # Expose the MFA verification state from the JWT so the frontend
        # can redirect to MFA setup when needed without a separate call.
        token_payload = getattr(request, 'token_payload', {})
        data['mfa_verified'] = token_payload.get('mfa_verified', False)
        return Response(data)


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
            email=serializer.validated_data.get('email'),
            method=serializer.validated_data.get('method', 'TOTP'),
        )

        if 'error' in result:
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

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
    permission_classes = [IsAuthenticated, IsMFAVerified]

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
    permission_classes = [IsAuthenticated, IsMFAVerified]

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


class MFAResendOTPView(APIView):
    """
    Resend email OTP during login.

    POST /api/mfa/resend-otp
    Requires a valid mfa_pending_token. Rate-limited to 3 per 5 minutes.
    """
    permission_classes = [AllowAny]
    throttle_classes = [MFAResendThrottle]

    def post(self, request):
        serializer = MFAResendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        pending_token = serializer.validated_data['mfa_pending_token']

        try:
            payload = decode_token(pending_token, token_type='mfa_pending')
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, KeyError, ValueError):
            return Response(
                {'error': 'Invalid or expired MFA token'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        try:
            user = User.objects.get(id=payload['sub'])
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not MFAManager.can_resend_otp(user):
            return Response(
                {'error': 'Please wait before requesting a new code'},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        otp_email = MFAManager.get_otp_email(user)
        if not otp_email:
            return Response(
                {'error': 'No email address configured'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from .mfa import _mask_email
        code = MFAManager.generate_email_otp(user)
        MFAManager._send_otp_email(user, code, otp_email)

        return Response({
            'success': True,
            'masked_email': _mask_email(otp_email),
        })


class HealthLiveView(APIView):
    """
    Liveness probe.

    GET /api/health/live
    """
    permission_classes = [AllowAny]
    throttle_classes = []  # Docker health checks hit this every 30s

    def get(self, request):
        return Response({'status': 'live'})


class HealthView(APIView):
    """
    Simple health check endpoint.

    GET /health/
    No auth required, lightweight, no DB queries
    """
    permission_classes = [AllowAny]
    authentication_classes = []  # Explicitly disable authentication
    throttle_classes = []

    def get(self, request):
        # Lightweight health check - no database queries
        return JsonResponse({"status": "healthy"})


def health(request):
    """
    Simple health check endpoint for Docker healthchecks.
    """
    return JsonResponse({"status": "ok"})


class HealthReadyView(APIView):
    """
    Readiness probe - checks all dependencies.

    GET /api/health/ready
    """
    permission_classes = [AllowAny]
    throttle_classes = []

    def get(self, request):
        errors = []

        # Check database
        try:
            connection.ensure_connection()
            db_ok = True
        except Exception as e:
            db_ok = False
            logger.error("health_check_db_failed", error=str(e))
            errors.append('database: unavailable')

        # Check ML engine
        from apps.screening.ml_engine import get_ml_engine
        ml_engine = get_ml_engine()
        ml_status = ml_engine.get_status()
        if not ml_status['ready']:
            errors.append(f"ml_engine: {ml_status.get('error', 'not ready')}")

        # Check crypto
        crypto_status = get_crypto_status()

        # Check Redis connectivity
        try:
            from django.core.cache import cache
            cache.set('_health_probe', '1', timeout=5)
            assert cache.get('_health_probe') == '1'
            redis_ok = True
        except Exception as e:
            redis_ok = False
            logger.error("health_check_redis_failed", error=str(e))
            errors.append('redis: unavailable')

        # Check Celery worker responsiveness (ping task)
        celery_ok = True
        celery_error = None
        try:
            from clinomic.celery import app as celery_app
            result = celery_app.control.ping(timeout=2, limit=1)
            celery_ok = bool(result)
            if not celery_ok:
                celery_error = 'no workers responded'
                # Warn but don't fail readiness — workers may be starting up
        except Exception as e:
            logger.error("health_check_celery_failed", error=str(e))
            celery_error = 'unavailable'
            # Celery ping failure is non-fatal; don't block health check

        if errors:
            return Response(
                {
                    'status': 'not ready',
                    'errors': errors,
                    'database': db_ok,
                    'ml_engine': ml_status,
                    'crypto': crypto_status,
                    'redis': redis_ok,
                    'celery': {'ok': celery_ok, 'error': celery_error},
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        return Response({
            'status': 'ready',
            'database': db_ok,
            'ml_engine': ml_status,
            'crypto': crypto_status,
            'redis': redis_ok,
            'celery': {'ok': celery_ok, 'error': celery_error},
        })


# ── Password Reset ─────────────────────────────────────────────────────────────


class ForgotPasswordView(APIView):
    """
    Initiate password reset.

    POST /api/auth/forgot-password
    Body: { "identifier": "<username or email>" }

    Always returns 200 so as not to enumerate accounts.
    Token is stored in the Redis cache for 15 minutes.
    """
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        import secrets
        from django.core.cache import cache

        identifier = (request.data.get('identifier') or '').strip()
        if not identifier:
            return Response({'detail': 'If an account with that identifier exists, a reset link has been sent.'})

        # Find user by username or email (case-insensitive)
        user = (
            User.objects.filter(username__iexact=identifier).first()
            or User.objects.filter(email__iexact=identifier).first()
        )

        if user and user.is_active:
            token = secrets.token_urlsafe(48)
            cache.set(f'pwd_reset_{token}', str(user.id), timeout=900)  # 15 min

            reset_url = f'{settings.FRONTEND_URL}/reset-password?token={token}'
            try:
                from django.core.mail import send_mail
                send_mail(
                    subject='Password Reset — Clinomic',
                    message=(
                        f'You requested a password reset for your Clinomic account.\n\n'
                        f'Click to reset your password:\n{reset_url}\n\n'
                        f'This link expires in 15 minutes.\n'
                        f'If you did not request this, ignore this email.'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except (OSError, Exception):
                logger.exception('Failed to send password reset email for user: %s', user.username)

            logger.info("Password reset requested for user: %s", user.username)

        # Generic response regardless of whether user was found
        return Response({'detail': 'If an account with that identifier exists, a reset link has been sent.'})


class ResetPasswordView(APIView):
    """
    Complete password reset.

    POST /api/auth/reset-password
    Body: { "token": "<token>", "new_password": "<password>" }
    """
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        from django.core.cache import cache
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        token = (request.data.get('token') or '').strip()
        new_password = request.data.get('new_password', '')

        if not token or not new_password:
            return Response(
                {'error': 'token and new_password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Atomically consume the token to prevent concurrent reuse.
        # cache.delete() returns True when the key existed and was removed,
        # making get-then-delete race-free for Django's Redis backend.
        cache_key = f'pwd_reset_{token}'
        user_id = cache.get(cache_key)
        if not user_id or not cache.delete(cache_key):
            return Response(
                {'error': 'Invalid or expired reset token'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'Invalid reset token'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            validate_password(new_password, user)
        except ValidationError as e:
            return Response({'error': list(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=['password'])

        # Revoke all existing refresh tokens on password change
        from .models import RefreshToken as RT
        RT.objects.filter(user=user, is_revoked=False).update(is_revoked=True)

        return Response({'detail': 'Password has been reset successfully.'})


class SetPasswordView(APIView):
    """
    Set password for a new account using the Django token from the credentials email.

    POST /api/auth/set-password
    Body: { "uid": "<base64-encoded user id>", "token": "<token>", "new_password": "<password>" }
    """
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_str
        from django.utils.http import urlsafe_base64_decode

        uid = (request.data.get('uid') or '').strip()
        token = (request.data.get('token') or '').strip()
        new_password = request.data.get('new_password', '')

        if not uid or not token or not new_password:
            return Response(
                {'error': 'uid, token, and new_password are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {'error': 'Invalid or expired link'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not default_token_generator.check_token(user, token):
            return Response(
                {'error': 'Invalid or expired link. Please ask your administrator to resend the invitation.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from django.contrib.auth.password_validation import validate_password
            validate_password(new_password, user)
        except ValidationError as e:
            return Response({'error': list(e.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=['password'])

        logger.info("Password set via credentials link for user: %s", user.username)

        return Response({
            'detail': 'Password has been set successfully. You can now log in.',
            'username': user.username,
        })


# ── Active Session Management ──────────────────────────────────────────────────

class SessionListView(APIView):
    """
    List the authenticated user's active refresh-token sessions.

    GET /api/auth/sessions
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from datetime import datetime, timezone as tz
        now = datetime.now(tz.utc)
        tokens = (
            request.user.refresh_tokens
            .filter(is_revoked=False, expires_at__gt=now)
            .order_by('-last_used_at')
        )
        result = []
        for t in tokens:
            result.append({
                'id': str(t.id),
                'created_at': t.created_at.isoformat(),
                'last_used_at': t.last_used_at.isoformat() if t.last_used_at else None,
                'expires_at': t.expires_at.isoformat(),
                'device_info': t.device_info or {},
            })
        return Response(result)


class SessionRevokeView(APIView):
    """
    Revoke a specific refresh-token session.

    DELETE /api/auth/sessions/<token_id>
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, token_id):
        from .models import RefreshToken as RT
        try:
            token = RT.objects.get(id=token_id, user=request.user)
        except RT.DoesNotExist:
            return Response({'error': 'Session not found'}, status=status.HTTP_404_NOT_FOUND)

        token.is_revoked = True
        token.save(update_fields=['is_revoked'])
        return Response({'detail': 'Session revoked'})


# ── Notifications ──────────────────────────────────────────────────────────────

class NotificationListView(APIView):
    """
    List notifications for the authenticated user.

    GET /api/notifications/
    Returns the 20 most recent notifications plus an unread count.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import Notification
        qs = Notification.objects.filter(user=request.user).order_by('-created_at')[:20]
        unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
        notifications = [
            {
                'id': str(n.id),
                'type': n.type,
                'title': n.title,
                'body': n.body,
                'is_read': n.is_read,
                'created_at': n.created_at.isoformat(),
            }
            for n in qs
        ]
        return Response({'unread_count': unread_count, 'notifications': notifications})


class NotificationMarkReadView(APIView):
    """
    Mark a notification as read.

    POST /api/notifications/<notification_id>/read
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, notification_id):
        from .models import Notification
        try:
            n = Notification.objects.get(id=notification_id, user=request.user)
        except Notification.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        n.is_read = True
        n.save(update_fields=['is_read'])
        return Response({'detail': 'Marked as read'})


# ── Admin User Management ───────────────────────────────────────────────────────

class AdminUserListView(APIView):
    """
    List and create users within the admin's organization.

    GET  /api/admin/users   — list all org users
    POST /api/admin/users   — create a new user in the org
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, IsOrgManager]

    def get(self, request):
        org = request.user.organization
        users = User.objects.filter(organization=org).order_by('name', 'username')
        # LAB users see all org users except SUPER_ADMIN
        if request.user.role == Role.LAB:
            users = users.exclude(role=Role.SUPER_ADMIN)
        data = [
            {
                'id': str(u.id),
                'username': u.username,
                'email': u.email or '',
                'name': u.name,
                'role': u.role,
                'is_active': u.is_active,
                'created_at': u.created_at.isoformat(),
            }
            for u in users
        ]
        return Response(data)

    def post(self, request):
        org = request.user.organization
        required = ['username', 'password', 'role']
        for field in required:
            if not request.data.get(field):
                return Response({'error': f'{field} is required'}, status=status.HTTP_400_BAD_REQUEST)

        username = request.data['username'].strip()
        email = (request.data.get('email') or '').strip() or None
        name = (request.data.get('name') or '').strip()
        role = request.data['role'].upper()
        password = request.data['password']

        if role not in Role.values:
            return Response({'error': f'Invalid role. Must be one of: {Role.values}'}, status=status.HTTP_400_BAD_REQUEST)

        # LAB users can create LAB and DOCTOR accounts (not SUPER_ADMIN)
        if request.user.role == Role.LAB and role not in (Role.LAB, Role.DOCTOR):
            return Response(
                {'error': 'You can only create LAB or DOCTOR accounts'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if User.objects.filter(username__iexact=username).exists():
            return Response({'error': 'Username already taken'}, status=status.HTTP_400_BAD_REQUEST)

        user = User(
            username=username,
            email=email,
            name=name,
            role=role,
            organization=org,
        )
        try:
            validate_password(password, user=user)
        except ValidationError as e:
            return Response({'error': e.messages}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(password)
        user.save()

        # Auto-create a Doctor record in the tenant schema when a DOCTOR
        # user is created, so they can immediately start screening.
        if role == Role.DOCTOR:
            try:
                from apps.screening.models import Doctor, Lab
                lab = Lab.objects.filter(is_active=True).order_by('created_at').first()
                if lab and not Doctor.objects.filter(email=user.email).exists():
                    doctor_code = f'D-{username.upper()}'
                    Doctor.objects.create(
                        code=doctor_code,
                        name=name or username,
                        email=user.email or '',
                        lab=lab,
                    )
            except Exception as exc:
                logger.warning('auto_create_doctor_failed user_id=%s error=%s', user.id, exc)

        # Send credentials email asynchronously (if email provided)
        if user.email:
            try:
                from apps.billing.tasks import send_credentials_email
                org_name = org.name if org else 'Clinomic'
                send_credentials_email.delay(str(user.id), org_name)
            except Exception as exc:
                logger.warning('send_credentials_email_failed user_id=%s error=%s', user.id, exc)

        return Response({
            'id': str(user.id),
            'username': user.username,
            'email': user.email or '',
            'name': user.name,
            'role': user.role,
            'is_active': user.is_active,
        }, status=status.HTTP_201_CREATED)


class AdminUserDetailView(APIView):
    """
    Update or deactivate a user within the admin's organization.

    PATCH  /api/admin/users/<user_id>  — update fields
    DELETE /api/admin/users/<user_id>  — soft-deactivate (is_active=False)
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, IsOrgManager]

    def _get_user(self, request, user_id):
        try:
            user = User.objects.get(id=user_id, organization=request.user.organization)
            # LAB users cannot manage SUPER_ADMIN users
            if request.user.role == Role.LAB and user.role == Role.SUPER_ADMIN:
                return None
            return user
        except User.DoesNotExist:
            return None

    def patch(self, request, user_id):
        user = self._get_user(request, user_id)
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        allowed = ['name', 'email', 'role', 'is_active']
        for field in allowed:
            if field in request.data:
                value = request.data[field]
                if field == 'role':
                    value = value.upper()
                    if value not in Role.values:
                        return Response({'error': f'Invalid role'}, status=status.HTTP_400_BAD_REQUEST)
                    # LAB users can only assign LAB or DOCTOR roles
                    if request.user.role == Role.LAB and value not in (Role.LAB, Role.DOCTOR):
                        return Response(
                            {'error': 'You can only assign LAB or DOCTOR roles'},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                setattr(user, field, value)

        if 'password' in request.data and request.data['password']:
            try:
                validate_password(request.data['password'], user=user)
            except ValidationError as e:
                return Response({'error': e.messages}, status=status.HTTP_400_BAD_REQUEST)
            user.set_password(request.data['password'])

        user.save()
        return Response({
            'id': str(user.id),
            'username': user.username,
            'email': user.email or '',
            'name': user.name,
            'role': user.role,
            'is_active': user.is_active,
        })

    def delete(self, request, user_id):
        user = self._get_user(request, user_id)
        if not user:
            return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

        if user.id == request.user.id:
            return Response({'error': 'Cannot deactivate your own account'}, status=status.HTTP_400_BAD_REQUEST)

        # ?permanent=true → hard-delete (only for already-inactive users)
        if request.query_params.get('permanent') == 'true':
            if user.is_active:
                return Response(
                    {'error': 'Deactivate the user first before permanently removing'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            user.delete()
            return Response({'detail': 'User permanently removed'})

        user.is_active = False
        user.save(update_fields=['is_active', 'updated_at'])
        return Response({'detail': 'User deactivated'})

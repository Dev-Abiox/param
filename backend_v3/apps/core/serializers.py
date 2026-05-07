"""
Serializers for Core API endpoints.
"""

from rest_framework import serializers

from .models import User


class LoginSerializer(serializers.Serializer):
    """Login request serializer."""
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)
    mfa_code = serializers.CharField(max_length=10, required=False, allow_blank=True)


class MFAVerifySerializer(serializers.Serializer):
    """MFA verification request serializer."""
    mfa_pending_token = serializers.CharField()
    mfa_code = serializers.CharField(max_length=10)
    remember_device = serializers.BooleanField(default=False, required=False)



class UserSerializer(serializers.ModelSerializer):
    """User data serializer."""
    organization_name = serializers.SerializerMethodField()
    doctor_code = serializers.SerializerMethodField()
    lab_code = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'name', 'role', 'organization_name', 'is_active', 'doctor_code', 'lab_code']
        read_only_fields = ['id', 'is_active']

    def get_organization_name(self, obj):
        return obj.organization.name if obj.organization else None

    def get_doctor_code(self, obj):
        """Return doctor code for DOCTOR role users matched by email."""
        if obj.role == 'DOCTOR' and obj.email and obj.organization:
            from apps.screening.models import Doctor
            from django_tenants.utils import schema_context
            with schema_context(obj.organization.schema_name):
                doctor = Doctor.objects.filter(email=obj.email, is_active=True).first()
            return doctor.code if doctor else None
        return None

    def get_lab_code(self, obj):
        """Return the primary lab code for the user."""
        if obj.role == 'LAB' and obj.organization:
            from apps.screening.models import Lab
            from django_tenants.utils import schema_context
            with schema_context(obj.organization.schema_name):
                lab = Lab.objects.filter(is_active=True).order_by('created_at').first()
            return lab.code if lab else None
        if obj.role == 'DOCTOR' and obj.email:
            from apps.screening.models import Doctor
            from django_tenants.utils import schema_context
            if not obj.organization:
                return None
            with schema_context(obj.organization.schema_name):
                doctor = Doctor.objects.filter(
                    email=obj.email, is_active=True
                ).select_related('lab').first()
            return doctor.lab.code if doctor and doctor.lab else None
        return None


class AdminUserUpdateSerializer(serializers.Serializer):
    """Strict allowlist for PATCH /api/admin/users/<id>.

    Defines the only fields an org admin can change on another user. Anything
    not declared here (e.g. username, mfa_verified, is_super_admin, organization)
    is silently ignored — the endpoint must not trust client-supplied identity
    fields beyond these.
    """
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    role = serializers.CharField(required=False)
    is_active = serializers.BooleanField(required=False)
    password = serializers.CharField(required=False, write_only=True, allow_blank=False, min_length=1)


class MFAResendOTPSerializer(serializers.Serializer):
    """MFA OTP resend request serializer."""
    mfa_pending_token = serializers.CharField()


class MFASetupSerializer(serializers.Serializer):
    """MFA setup request serializer.

    `email` is intentionally NOT accepted — recovery_email is always derived
    server-side from `user.email` to prevent synthetic frontend values from
    poisoning the OTP destination (see feedback_mfa_recovery_email memory).
    """
    method = serializers.ChoiceField(choices=['EMAIL'], default='EMAIL', required=False)


class MFACodeSerializer(serializers.Serializer):
    """MFA code submission serializer."""
    code = serializers.CharField(max_length=10)


class MFAStatusSerializer(serializers.Serializer):
    """MFA status response serializer."""
    enabled = serializers.BooleanField()
    is_enabled = serializers.BooleanField()
    verified = serializers.BooleanField()
    recovery_email = serializers.BooleanField()
    backup_codes_remaining = serializers.IntegerField()
    mfa_method = serializers.CharField()
    mfa_required_for_role = serializers.BooleanField()


class HealthSerializer(serializers.Serializer):
    """Health check response serializer."""
    status = serializers.CharField()
    database = serializers.BooleanField(required=False)
    ml_engine = serializers.DictField(required=False)
    crypto = serializers.DictField(required=False)

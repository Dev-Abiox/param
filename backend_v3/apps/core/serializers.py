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


class TokenRefreshSerializer(serializers.Serializer):
    """Token refresh request serializer."""
    refresh_token = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    """Logout request serializer."""
    refresh_token = serializers.CharField()


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
        if obj.role == 'DOCTOR' and obj.email:
            from apps.screening.models import Doctor
            doctor = Doctor.objects.filter(email=obj.email, is_active=True).first()
            return doctor.code if doctor else None
        return None

    def get_lab_code(self, obj):
        """Return lab code for LAB role users matched by organization."""
        if obj.role == 'LAB' and obj.organization:
            from apps.screening.models import Lab
            lab = Lab.objects.filter(name=obj.organization.name, is_active=True).first()
            return lab.code if lab else None
        return None


class MFASetupSerializer(serializers.Serializer):
    """MFA setup request serializer."""
    email = serializers.EmailField(required=False)


class MFACodeSerializer(serializers.Serializer):
    """MFA code submission serializer."""
    code = serializers.CharField(max_length=10)


class MFAStatusSerializer(serializers.Serializer):
    """MFA status response serializer."""
    enabled = serializers.BooleanField()
    verified = serializers.BooleanField()
    recovery_email = serializers.BooleanField()
    backup_codes_remaining = serializers.IntegerField()


class HealthSerializer(serializers.Serializer):
    """Health check response serializer."""
    status = serializers.CharField()
    database = serializers.BooleanField(required=False)
    ml_engine = serializers.DictField(required=False)
    crypto = serializers.DictField(required=False)

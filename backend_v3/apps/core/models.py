"""
Core models for Clinomic B12 Screening Platform.

Includes multi-tenant organization model, custom user model, and MFA settings.
"""

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django_tenants.models import DomainMixin, TenantMixin


class Organization(TenantMixin):
    """
    Multi-tenant organization model.
    Each organization (lab, hospital) has isolated data.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    tier = models.CharField(
        max_length=50,
        choices=[
            ('standard', 'Standard'),
            ('enterprise', 'Enterprise'),
            ('pilot', 'Pilot'),
        ],
        default='standard'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    auto_create_schema = True

    class Meta:
        db_table = 'organizations'
        verbose_name = 'Organization'
        verbose_name_plural = 'Organizations'

    def __str__(self):
        return self.name


class Domain(DomainMixin):
    """
    Domain model for tenant routing.
    """
    pass


class Role(models.TextChoices):
    """User roles in the system."""
    ADMIN = 'ADMIN', 'Administrator'
    LAB = 'LAB', 'Lab Technician'
    DOCTOR = 'DOCTOR', 'Doctor'


class UserManager(BaseUserManager):
    """Custom user manager for email-based authentication."""

    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError('Username is required')
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', Role.ADMIN)
        return self.create_user(username, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom user model with role-based access control.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(blank=True, null=True)
    name = models.CharField(max_length=255, blank=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.LAB
    )

    # Organization reference (for non-super users)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='users'
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = []

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return f"{self.username} ({self.role})"

    @property
    def is_super_admin(self):
        return self.is_superuser


class MFASettings(models.Model):
    """
    MFA configuration for a user.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='mfa_settings'
    )
    is_enabled = models.BooleanField(default=False)
    secret_key = models.CharField(max_length=32, blank=True)  # Encrypted TOTP secret
    backup_codes = models.JSONField(default=list)  # Hashed backup codes
    recovery_email = models.EmailField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'mfa_settings'
        verbose_name = 'MFA Settings'
        verbose_name_plural = 'MFA Settings'

    def __str__(self):
        status = 'enabled' if self.is_enabled else 'disabled'
        return f"MFA for {self.user.username} ({status})"


class RefreshToken(models.Model):
    """
    Refresh token storage for JWT rotation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='refresh_tokens'
    )
    token_hash = models.CharField(max_length=64, unique=True)  # SHA256 hash
    device_info = models.JSONField(default=dict, blank=True)
    is_revoked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'refresh_tokens'
        indexes = [
            models.Index(fields=['user', 'token_hash']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"RefreshToken for {self.user.username}"


class AuditLogEntry(models.Model):
    """
    Immutable audit log with hash chain for compliance.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sequence = models.BigIntegerField()
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

    actor = models.CharField(max_length=255)  # Username or system
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=255, blank=True)
    details = models.JSONField(default=dict)

    # Hash chain for immutability verification
    previous_hash = models.CharField(max_length=64)
    entry_hash = models.CharField(max_length=64)
    signature = models.CharField(max_length=128)  # HMAC signature

    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        db_table = 'audit_log_entries'
        ordering = ['-sequence']
        indexes = [
            models.Index(fields=['organization', 'sequence']),
            models.Index(fields=['organization', 'timestamp']),
            models.Index(fields=['actor', 'timestamp']),
        ]

    def __str__(self):
        return f"[{self.sequence}] {self.actor}: {self.action}"

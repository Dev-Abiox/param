"""
Core models for Clinomic B12 Screening Platform.

Includes multi-tenant organization model, custom user model, and MFA settings.
"""

import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django_tenants.models import DomainMixin, TenantMixin


def _default_onboarding_status():
    return {'lab_added': False, 'doctor_added': False, 'user_invited': False, 'completed': False}


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

    onboarding_status = models.JSONField(default=_default_onboarding_status)

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
    SUPER_ADMIN = 'SUPER_ADMIN', 'Platform Administrator'
    LAB = 'LAB', 'Lab Manager'
    DOCTOR = 'DOCTOR', 'Doctor'


class LabSubRole(models.TextChoices):
    """
    Sub-roles inside a Lab tenant (role=LAB) used to implement
    purpose-limited access per DPDP Act §4.  See DATA_MINIMISATION_AUDIT.md
    and the P1-19 section of the DPDP POA.

    Ordering (least → most permissive):
        receptionist  → demographics + status + billing
        technician    → + raw CBC values
        pathologist   → + software workflow recommendations / narrative
        lab_admin     → + tenant user management + audit log

    Empty string = legacy/unscoped LAB user retaining full access (used
    during rollout so existing accounts keep working).
    """
    UNSCOPED     = '',             '(unscoped — legacy full-access LAB user)'
    RECEPTIONIST = 'receptionist', 'Lab Receptionist'
    TECHNICIAN   = 'technician',   'Lab Technician'
    PATHOLOGIST  = 'pathologist',  'Lab Pathologist'
    LAB_ADMIN    = 'lab_admin',    'Lab Administrator'


# Rank map for least-to-most-permissive comparisons.  The empty-string
# UNSCOPED level is treated as fully-permissive (legacy behaviour)
# so no call site is broken when a user has not been assigned a sub-role.
_LAB_SUB_ROLE_RANK = {
    LabSubRole.RECEPTIONIST: 1,
    LabSubRole.TECHNICIAN: 2,
    LabSubRole.PATHOLOGIST: 3,
    LabSubRole.LAB_ADMIN: 4,
    LabSubRole.UNSCOPED: 99,  # treated as highest so unscoped users pass any floor
}


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
        extra_fields.setdefault('role', Role.SUPER_ADMIN)
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
    # Sub-role inside a Lab tenant.  Ignored for role != LAB.  The empty
    # default ('unscoped') preserves legacy full-access behaviour for
    # accounts that existed before P1-19.  See LabSubRole docstring.
    lab_sub_role = models.CharField(
        max_length=20,
        choices=LabSubRole.choices,
        default=LabSubRole.UNSCOPED,
        blank=True,
    )

    # Organization reference (for non-super users)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.SET_NULL,
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
        indexes = [
            models.Index(fields=['organization', 'is_active']),
            models.Index(fields=['email']),
            models.Index(fields=['role', 'is_active']),
        ]
        constraints = [
            # Partial-unique email: enforce uniqueness only when email is
            # actually set. Empty/NULL slots are allowed to repeat because
            # a user profile may legitimately have no email on file (e.g.
            # a lab-tech account provisioned without one). Postgres honours
            # partial indexes so this compiles to a real UNIQUE constraint.
            models.UniqueConstraint(
                fields=['email'],
                condition=~models.Q(email__isnull=True) & ~models.Q(email=''),
                name='unique_user_email_when_set',
            ),
        ]

    def __str__(self):
        return f"{self.username} ({self.role})"

    @property
    def is_super_admin(self):
        return self.is_superuser or self.role == Role.SUPER_ADMIN

    # ── Lab sub-role capability helpers (P1-19) ───────────────────────
    #
    # These helpers return True when the user is authorised to perform
    # the capability at issue.  They fail open for SUPER_ADMIN, DOCTOR,
    # and legacy-unscoped LAB users so existing behaviour is preserved
    # during rollout.  Once every LAB user has been assigned a sub-role,
    # remove the UNSCOPED short-circuit in each helper.
    def _lab_rank(self) -> int:
        if self.role != Role.LAB:
            return 0
        return _LAB_SUB_ROLE_RANK.get(self.lab_sub_role, 99)

    def can_view_demographics(self) -> bool:
        """Patient id, age bucket, sex, status — receptionist and up."""
        if self.is_super_admin or self.role == Role.DOCTOR:
            return True
        if self.role != Role.LAB:
            return False
        return self._lab_rank() >= _LAB_SUB_ROLE_RANK[LabSubRole.RECEPTIONIST]

    def can_view_cbc_values(self) -> bool:
        """Raw CBC numerics — technician and up."""
        if self.is_super_admin or self.role == Role.DOCTOR:
            return True
        if self.role != Role.LAB:
            return False
        return self._lab_rank() >= _LAB_SUB_ROLE_RANK[LabSubRole.TECHNICIAN]

    def can_view_recommendation(self) -> bool:
        """Software workflow recommendation / narrative — pathologist and up."""
        if self.is_super_admin or self.role == Role.DOCTOR:
            return True
        if self.role != Role.LAB:
            return False
        return self._lab_rank() >= _LAB_SUB_ROLE_RANK[LabSubRole.PATHOLOGIST]

    def can_manage_lab_users(self) -> bool:
        """Tenant user management + audit-log access — lab_admin only."""
        if self.is_super_admin:
            return True
        if self.role != Role.LAB:
            return False
        return self._lab_rank() >= _LAB_SUB_ROLE_RANK[LabSubRole.LAB_ADMIN]


class MFAMethod(models.TextChoices):
    """Supported MFA verification methods."""
    TOTP = 'TOTP', 'Authenticator App'
    EMAIL = 'EMAIL', 'Email Code'


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
    mfa_method = models.CharField(
        max_length=10,
        choices=MFAMethod.choices,
        default=MFAMethod.TOTP,
    )
    secret_key = models.TextField(blank=True)  # Encrypted TOTP secret (Fernet ciphertext)
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


class TrustedDevice(models.Model):
    """
    Stores trusted device tokens so users can skip MFA for 30 days.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='trusted_devices')
    token_hash = models.CharField(max_length=64, unique=True)
    user_agent = models.TextField(blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'trusted_devices'
        indexes = [
            models.Index(fields=['user', 'token_hash']),
            models.Index(fields=['expires_at']),
        ]

    def __str__(self):
        return f"TrustedDevice for {self.user.username}"


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


class Notification(models.Model):
    """
    User-facing notification (high-risk alerts, system messages, etc.).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    type = models.CharField(max_length=50, default='info')   # 'high_risk', 'info', 'alert'
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
        ]

    def __str__(self):
        return f"Notification({self.type}) for {self.user.username}: {self.title}"

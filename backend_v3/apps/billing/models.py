"""
Billing models for Clinomic SaaS Engine.

All models are in SHARED_APPS (public schema) — they are organisation-level,
not per-tenant-schema.
"""

import logging
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class SubscriptionPlan(models.Model):
    """
    Product catalogue: the three tiers available for purchase.
    Seeded by the initial data migration — do not create manually.
    """
    STARTER = 'starter'
    PROFESSIONAL = 'professional'
    ENTERPRISE = 'enterprise'

    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    monthly_limit = models.IntegerField()          # -1 = unlimited
    price_monthly = models.DecimalField(max_digits=10, decimal_places=2)  # INR
    razorpay_plan_id = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_plans'
        ordering = ['price_monthly']

    def __str__(self):
        return f"{self.display_name} ({self.monthly_limit} screenings/mo)"


class TenantSubscription(models.Model):
    """
    One subscription record per Organisation.
    `current_period_count` is atomically incremented by the billing Celery task
    every time a screening is completed.
    """
    class Status(models.TextChoices):
        TRIAL = 'trial', 'Trial'
        ACTIVE = 'active', 'Active'
        CANCELLED = 'cancelled', 'Cancelled'
        PAST_DUE = 'past_due', 'Past Due'
        EXPIRED = 'expired', 'Expired'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        'core.Organization',
        on_delete=models.PROTECT,
        related_name='subscription',
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='subscriptions',
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.TRIAL,
    )
    razorpay_sub_id = models.CharField(max_length=100, blank=True, default='', db_index=True)

    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    current_period_count = models.IntegerField(default=0)

    trial_end = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_subscriptions'

    def __str__(self):
        return f"{self.organization.name} — {self.plan.display_name} ({self.status})"

    ALLOWED_TRANSITIONS = {
        Status.TRIAL:     {Status.ACTIVE, Status.CANCELLED, Status.EXPIRED},
        Status.ACTIVE:    {Status.CANCELLED, Status.PAST_DUE, Status.EXPIRED},
        Status.PAST_DUE:  {Status.ACTIVE, Status.CANCELLED, Status.EXPIRED},
        Status.CANCELLED: {Status.ACTIVE},   # only via confirmed payment
        Status.EXPIRED:   {Status.ACTIVE},   # only via confirmed payment
    }

    def transition_to(self, new_status: str) -> None:
        """Validate and set a new subscription status.

        Raises ValueError if the transition is not allowed.
        Caller must wrap the subsequent .save() in transaction.atomic().
        """
        allowed = self.ALLOWED_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f'Invalid status transition: {self.status} → {new_status}'
            )
        old = self.status
        self.status = new_status
        logger.info('subscription.transition org=%s %s→%s', self.organization_id, old, new_status)

    @property
    def is_over_limit(self) -> bool:
        lim = self.plan.monthly_limit
        return lim != -1 and self.current_period_count >= lim


class UsageRecord(models.Model):
    """
    Monthly snapshot created by the `compute_monthly_rollups` Celery task
    on the 1st of each month before counters are reset.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.PROTECT,
        related_name='usage_records',
    )
    period_start = models.DateField()
    period_end = models.DateField()
    screening_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'billing_usage_records'
        unique_together = ['organization', 'period_start']
        ordering = ['-period_start']

    def __str__(self):
        return f"{self.organization.name} {self.period_start} — {self.screening_count} screenings"


class PaymentEvent(models.Model):
    """
    Raw Razorpay webhook events stored for idempotency and audit.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payment_events',
    )
    razorpay_event_id = models.CharField(max_length=200, unique=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'billing_payment_events'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.event_type} — {self.razorpay_event_id}"


# ── API Key Management ──────────────────────────────────────────────────────────

VALID_SCOPES = frozenset({
    'screening:read',
    'screening:write',
    'analytics:read',
})


class APIKey(models.Model):
    """
    API keys for programmatic access to the platform.

    The raw key is generated with secrets.token_urlsafe(32) and shown to the
    user exactly once at creation time.  Only the SHA-256 hex digest is stored
    so that a database breach cannot be used to impersonate callers.

    Lives in the shared (public) schema — one key spans all tenants of an org.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.CASCADE,
        related_name='api_keys',
    )
    name = models.CharField(
        max_length=100,
        help_text='Human-readable label for this key (e.g. "CI Pipeline").',
    )
    key_hash = models.CharField(
        max_length=64,
        unique=True,
        help_text='SHA-256 hex digest of the raw key — never store the raw key.',
    )
    scopes = models.JSONField(
        default=list,
        help_text=(
            'List of granted permission scopes. '
            'Valid values: "screening:read", "screening:write", "analytics:read".'
        ),
    )
    rate_limit = models.IntegerField(
        default=60,
        help_text='Maximum requests per minute allowed for this key.',
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_api_keys',
    )
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_api_keys'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.organization.name})"

    def has_scope(self, scope: str) -> bool:
        """Return True if this key grants the requested scope."""
        return scope in (self.scopes or [])


# ── Tenant Webhook Endpoints ────────────────────────────────────────────────────

def _default_webhook_secret():
    """Generate a 32-character URL-safe random secret for a new webhook endpoint."""
    return secrets.token_urlsafe(32)[:32]


class WebhookEndpoint(models.Model):
    """
    A tenant-configured HTTP endpoint that receives signed event notifications.

    Supported event names
    ---------------------
    - ``screening.completed``  — fired when a screening result is saved.
    - ``screening.high_risk``  — fired when risk_class == DEFICIENT (3).
    - ``consent.revoked``      — fired when a patient revokes consent.
    - ``subscription.changed`` — fired when the subscription plan changes.

    Security
    --------
    Each endpoint has a randomly generated 32-character ``secret``.  Every
    delivery POSTs a JSON body that includes the event name, an ISO-8601
    timestamp, and the event data.  The body is signed with HMAC-SHA256 using
    the secret and the digest is sent as::

        X-Clinomic-Signature: sha256=<hex-digest>

    Receivers should verify this signature before processing the payload.

    Lives in the shared (public) schema — one record per registered URL.
    """

    SUPPORTED_EVENTS = [
        'screening.completed',
        'screening.high_risk',
        'consent.revoked',
        'subscription.changed',
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'core.Organization',
        on_delete=models.CASCADE,
        related_name='webhook_endpoints',
    )
    url = models.URLField(
        max_length=500,
        help_text='The HTTPS URL that will receive POST requests for subscribed events.',
    )
    events = models.JSONField(
        default=list,
        help_text=(
            'List of event names this endpoint is subscribed to.  '
            'Valid values: "screening.completed", "screening.high_risk", '
            '"consent.revoked", "subscription.changed".'
        ),
    )
    secret = models.CharField(
        max_length=64,
        default=_default_webhook_secret,
        help_text='HMAC-SHA256 signing secret.  Shown once at creation time.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_webhook_endpoints'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.organization.name} → {self.url}"

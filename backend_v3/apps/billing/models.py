"""
Billing models for Clinomic SaaS Engine.

All models are in SHARED_APPS (public schema) — they are organisation-level,
not per-tenant-schema.
"""

import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


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

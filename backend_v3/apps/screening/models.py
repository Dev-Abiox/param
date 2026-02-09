"""
Screening models for Clinomic B12 Screening Platform.

Includes Patient, Lab, Doctor, Screening, and Consent models.
All models are tenant-aware through django-tenants.
"""

import uuid

from django.db import models

from apps.core.crypto import decrypt_field, encrypt_field


class Lab(models.Model):
    """
    Laboratory/clinic that performs screenings.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)  # e.g., LAB-2024-001
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
    address = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'labs'
        verbose_name = 'Lab'
        verbose_name_plural = 'Labs'

    def __str__(self):
        return f"{self.code} - {self.name}"


class Doctor(models.Model):
    """
    Doctor/physician associated with a lab.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True)  # e.g., D201
    name = models.CharField(max_length=255)
    department = models.CharField(max_length=100, blank=True)
    specialization = models.CharField(max_length=100, blank=True)
    lab = models.ForeignKey(
        Lab,
        on_delete=models.CASCADE,
        related_name='doctors'
    )
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'doctors'
        verbose_name = 'Doctor'
        verbose_name_plural = 'Doctors'

    def __str__(self):
        return f"{self.code} - {self.name}"


class Patient(models.Model):
    """
    Patient record with encrypted PHI.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient_id = models.CharField(max_length=100)  # External patient ID
    name_encrypted = models.TextField()  # Encrypted patient name (PHI)
    age = models.PositiveIntegerField()
    sex = models.CharField(
        max_length=1,
        choices=[('M', 'Male'), ('F', 'Female')]
    )

    lab = models.ForeignKey(
        Lab,
        on_delete=models.PROTECT,
        related_name='patients'
    )
    referring_doctor = models.ForeignKey(
        Doctor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='patients'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'patients'
        unique_together = ['patient_id']
        verbose_name = 'Patient'
        verbose_name_plural = 'Patients'

    def __str__(self):
        return f"Patient {self.patient_id}"

    @property
    def name(self) -> str:
        """Decrypt and return patient name."""
        return decrypt_field(self.name_encrypted)

    @name.setter
    def name(self, value: str):
        """Encrypt and store patient name."""
        self.name_encrypted = encrypt_field(value)


class RiskClass(models.IntegerChoices):
    """B12 deficiency risk classification."""
    NORMAL = 1, 'Normal'
    BORDERLINE = 2, 'Borderline'
    DEFICIENT = 3, 'Deficient'


class Screening(models.Model):
    """
    B12 screening result with full audit trail.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name='screenings'
    )
    lab = models.ForeignKey(
        Lab,
        on_delete=models.PROTECT,
        related_name='screenings'
    )
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='screenings'
    )
    performed_by = models.CharField(max_length=255)  # Username

    # Classification result
    risk_class = models.IntegerField(choices=RiskClass.choices)
    label_text = models.CharField(max_length=50)
    probabilities = models.JSONField()  # {normal: 0.x, borderline: 0.x, deficient: 0.x}
    rules_fired = models.JSONField(default=list)

    # CBC data snapshot
    cbc_snapshot = models.JSONField()

    # Calculated indices
    indices = models.JSONField(default=dict)

    # Model tracking
    model_version = models.CharField(max_length=50)
    model_artifact_hash = models.CharField(max_length=64)

    # Reproducibility hashes
    request_hash = models.CharField(max_length=64)
    response_hash = models.CharField(max_length=64)
    screening_hash = models.CharField(max_length=64)

    # Consent reference
    consent_id = models.CharField(max_length=100, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'screenings'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['lab', '-created_at']),
            models.Index(fields=['doctor', '-created_at']),
            models.Index(fields=['patient', '-created_at']),
        ]

    def __str__(self):
        return f"Screening {self.id} - {self.label_text}"


class Consent(models.Model):
    """
    Patient consent record for screening.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name='consents'
    )

    consent_type = models.CharField(max_length=50, default='screening')
    consent_text = models.TextField()
    consented_by = models.CharField(max_length=255)  # Who recorded consent
    consent_method = models.CharField(
        max_length=50,
        choices=[
            ('verbal', 'Verbal'),
            ('written', 'Written'),
            ('electronic', 'Electronic'),
        ],
        default='verbal'
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ('active', 'Active'),
            ('revoked', 'Revoked'),
            ('expired', 'Expired'),
        ],
        default='active'
    )

    consented_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'consents'
        ordering = ['-consented_at']
        indexes = [
            models.Index(fields=['patient', 'status']),
        ]

    def __str__(self):
        return f"Consent for {self.patient.patient_id} ({self.status})"

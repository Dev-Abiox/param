"""
Screening models for Clinomic B12 Screening Platform.

Includes Patient, Lab, Doctor, Screening, and Consent models.
All models are tenant-aware through django-tenants.
"""

import uuid

from django.db import models

from apps.core.crypto import CryptoError, decrypt_field, encrypt_field
from apps.core.fields import EncryptedJSONField


# ── Age bucketing ─────────────────────────────────────────────────────────────
# These labels MUST match apps.analytics.views.PopulationCohortsView.AGE_GROUPS
# so that the denormalised `age_bucket` column can be filter-joined to the
# cohort labels in population-level analytics.
AGE_BUCKET_PEDIATRIC = 'pediatric'
AGE_BUCKET_YOUNG = 'young_adult'
AGE_BUCKET_MIDDLE = 'middle_aged'
AGE_BUCKET_ELDERLY = 'elderly'
AGE_BUCKET_UNKNOWN = ''

AGE_BUCKET_CHOICES = [
    (AGE_BUCKET_PEDIATRIC, 'Pediatric (0-17)'),
    (AGE_BUCKET_YOUNG,     'Young Adult (18-39)'),
    (AGE_BUCKET_MIDDLE,    'Middle Aged (40-59)'),
    (AGE_BUCKET_ELDERLY,   'Elderly (60+)'),
]


def age_bucket_for(age) -> str:
    """Coarse age bucket used by analytics.

    Buckets are deliberately wide (pediatric / young / middle / elderly)
    so the denormalised column is low-sensitivity demographic context,
    not a precise PHI value.  The raw age stays encrypted on Patient and
    inside ``cbc_snapshot_enc``.
    """
    if age is None or age == '':
        return AGE_BUCKET_UNKNOWN
    try:
        age_int = int(age)
    except (ValueError, TypeError):
        return AGE_BUCKET_UNKNOWN
    if age_int < 0:
        return AGE_BUCKET_UNKNOWN
    if age_int < 18:
        return AGE_BUCKET_PEDIATRIC
    if age_int < 40:
        return AGE_BUCKET_YOUNG
    if age_int < 60:
        return AGE_BUCKET_MIDDLE
    return AGE_BUCKET_ELDERLY


def sex_code_for(value) -> str:
    """Normalise whatever the CBC record calls ``Sex`` into an M/F/empty code."""
    if value is None or value == '':
        return ''
    v = str(value).strip().upper()
    if v in ('M', 'MALE'):
        return 'M'
    if v in ('F', 'FEMALE'):
        return 'F'
    return ''


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

    # Patient PDF Disclosure Spec — Option A gate.  When False (the
    # default for all labs) the Workflow Recommendations table is
    # withheld from the patient-facing PDF entirely.  The on-screen
    # ResultPanel cards are unaffected — clinicians still see them.
    # Flip-to-True per lab is reserved for Option B once counsel has
    # signed off on the disclosure language and the lab has confirmed
    # pathologist sign-off + DPO email + grievance email.  No admin UI
    # exposes this flag yet; flip it manually via shell/SQL during the
    # commercial-launch readiness audit.
    patient_pdf_workflow_recs_enabled = models.BooleanField(
        default=False,
        help_text=(
            "If True, render the rule-based Workflow Recommendations "
            "section on patient-facing PDFs for screenings performed "
            "at this lab.  Default False until counsel sign-off and "
            "lab signature workflow are both in place."
        ),
    )

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
        on_delete=models.PROTECT,
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
    name_encrypted = models.TextField()   # Encrypted patient name (PHI)
    age_encrypted = models.TextField(blank=True, null=True)  # Encrypted patient age (PHI)
    sex_encrypted = models.TextField(blank=True, null=True)  # Encrypted patient sex (PHI)

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
        unique_together = ['patient_id', 'lab']
        verbose_name = 'Patient'
        verbose_name_plural = 'Patients'

    def __str__(self):
        return f"Patient {self.patient_id}"

    @property
    def name(self) -> str:
        """Decrypt and return patient name."""
        try:
            return decrypt_field(self.name_encrypted)
        except CryptoError:
            return '[decryption error]'

    @name.setter
    def name(self, value: str):
        """Encrypt and store patient name."""
        self.name_encrypted = encrypt_field(value)

    @property
    def age(self) -> int:
        """Decrypt and return patient age as an integer."""
        try:
            val = decrypt_field(self.age_encrypted)
        except CryptoError:
            return 0
        try:
            return int(val) if val else 0
        except (ValueError, TypeError):
            return 0

    @age.setter
    def age(self, value) -> None:
        self.age_encrypted = encrypt_field(str(int(value)))

    @property
    def sex(self) -> str:
        """Decrypt and return patient sex."""
        try:
            return decrypt_field(self.sex_encrypted) or ''
        except CryptoError:
            return ''

    @sex.setter
    def sex(self, value: str) -> None:
        self.sex_encrypted = encrypt_field(str(value))


class RiskClass(models.IntegerChoices):
    """B12 deficiency risk classification."""
    NORMAL = 1, 'Normal'
    BORDERLINE = 2, 'Borderline'
    DEFICIENT = 3, 'Deficient'


class ScreeningStatus(models.TextChoices):
    """Lab work queue status for a screening record."""
    PENDING = 'pending', 'Pending'
    IN_PROGRESS = 'in_progress', 'In Progress'
    COMPLETED = 'completed', 'Completed'


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
        on_delete=models.PROTECT,
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

    # CBC data snapshot (PHI — age, sex, lab values).
    #
    # ``cbc_snapshot_enc`` holds the Fernet-encrypted JSON and is the
    # authoritative store for all new rows.  ``cbc_snapshot`` is the
    # legacy unencrypted JSONField kept only so we can read rows that
    # were written before the DPDP encryption rollout; the data
    # migration in this release backfills the new field and blanks the
    # legacy one.  Readers should go through ``Screening.get_cbc_dict()``
    # which encapsulates the prefer-encrypted-with-legacy-fallback read
    # order.
    cbc_snapshot_enc = EncryptedJSONField(null=True, blank=True)
    cbc_snapshot = models.JSONField(default=dict, blank=True)

    # Non-PHI denormalised columns derived from cbc_snapshot at write
    # time.  These exist so analytics queries can filter on coarse
    # demographics without having to JSON-query the encrypted blob.
    age_bucket = models.CharField(
        max_length=20, choices=AGE_BUCKET_CHOICES,
        blank=True, default='', db_index=True,
    )
    sex_code = models.CharField(
        max_length=1, blank=True, default='', db_index=True,
        help_text="Normalised sex code: 'M', 'F', or ''.",
    )

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

    # Work queue status (3.2)
    status = models.CharField(
        max_length=20,
        choices=ScreeningStatus.choices,
        default=ScreeningStatus.PENDING,
    )

    # Doctor review workflow (3.3)
    is_reviewed = models.BooleanField(default=False)
    review_outcome = models.CharField(
        max_length=20,
        choices=[('approved', 'Approved'), ('flagged', 'Flagged')],
        null=True,
        blank=True,
    )
    clinical_note = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.CharField(max_length=255, blank=True)

    # Clinical narrative (Feature 8)
    narrative = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'screenings'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['lab', '-created_at']),
            models.Index(fields=['doctor', '-created_at']),
            models.Index(fields=['patient', '-created_at']),
            models.Index(fields=['status', '-created_at'], name='screening_status_idx'),
        ]

    def __str__(self):
        return f"Screening {self.id} - {self.label_text}"

    # ── Save-path auto-migration ──────────────────────────────────────
    # Existing callers write ``cbc_snapshot=cbc`` directly on create().
    # Transparently move that plaintext dict into the encrypted field
    # and populate the denormalised columns before the row hits the DB.
    # This means no caller needs to change, and legacy and new writes
    # converge on the encrypted storage.
    def save(self, *args, **kwargs):
        if self.cbc_snapshot and not self.cbc_snapshot_enc:
            self.set_cbc_dict(dict(self.cbc_snapshot))
        elif self.cbc_snapshot_enc and (
            not self.age_bucket or not self.sex_code
        ):
            # Encrypted payload already present but denorm fields not yet
            # populated (e.g. direct assignment to cbc_snapshot_enc).
            src = self.cbc_snapshot_enc if isinstance(self.cbc_snapshot_enc, dict) else {}
            if not self.age_bucket:
                self.age_bucket = age_bucket_for(src.get('Age', src.get('age')))
            if not self.sex_code:
                self.sex_code = sex_code_for(src.get('Sex', src.get('sex')))
        super().save(*args, **kwargs)

    # ── PHI-safe accessors ────────────────────────────────────────────
    def get_cbc_dict(self) -> dict:
        """Return the decrypted CBC snapshot dict for this screening.

        Prefers ``cbc_snapshot_enc`` (Fernet-encrypted, the new storage).
        Falls back to the legacy plaintext ``cbc_snapshot`` JSONField for
        rows written before the DPDP encryption rollout.  Always returns
        a dict — never None — so callers can safely ``.get(...)`` on it.
        """
        if self.cbc_snapshot_enc:
            return self.cbc_snapshot_enc
        return self.cbc_snapshot or {}

    def set_cbc_dict(self, cbc: dict) -> None:
        """Store the CBC snapshot under the encrypted column and populate
        the non-PHI denormalised columns ``age_bucket`` and ``sex_code``.
        Writes an empty dict to the legacy ``cbc_snapshot`` column so
        new rows never retain plaintext there.
        """
        cbc = cbc or {}
        self.cbc_snapshot_enc = cbc
        self.cbc_snapshot = {}
        age = cbc.get('Age', cbc.get('age'))
        sex = cbc.get('Sex', cbc.get('sex'))
        self.age_bucket = age_bucket_for(age)
        self.sex_code = sex_code_for(sex)


class BulkImportJob(models.Model):
    """
    Tracks a CSV bulk-import job submitted by a LAB user.

    The Celery task processes rows asynchronously and updates this record.
    Clients poll GET /api/screening/bulk-import/<id>/status for progress.
    """
    class JobStatus(models.TextChoices):
        PENDING    = 'pending',    'Pending'
        PROCESSING = 'processing', 'Processing'
        DONE       = 'done',       'Done'
        FAILED     = 'failed',     'Failed'

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    submitted_by   = models.CharField(max_length=255)
    status         = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.PENDING)
    total_rows     = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    failed_rows    = models.IntegerField(default=0)
    error_detail   = models.JSONField(default=list)   # [{row, error}, ...]
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bulk_import_jobs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at'], name='bulkimport_created_idx'),
        ]

    def __str__(self):
        return f"BulkImportJob {self.id} [{self.status}]"


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

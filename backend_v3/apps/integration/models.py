"""
Integration adapter models — connects external LIS systems to Clinomic screening.

Each Organization (tenant) can configure one or more IntegrationEndpoints,
each representing a connection to an external LIS. When the LIS pushes CBC
data (via HL7v2 ORU, FHIR Observation, REST JSON, or CSV), the adapter
parses it, runs the Clinomic B12 screening ML model, and pushes the result
back to the LIS in the requested format.
"""

import uuid

from django.db import models


class IntegrationFormat(models.TextChoices):
    """Supported inbound/outbound data formats."""
    HL7V2 = 'hl7v2', 'HL7 v2.x (ORU/ORM)'
    FHIR_R4 = 'fhir_r4', 'FHIR R4 (Observation/DiagnosticReport)'
    JSON = 'json', 'REST JSON'
    CSV = 'csv', 'CSV flat file'


class IntegrationEndpoint(models.Model):
    """
    Configuration for an external LIS integration.

    One tenant can have multiple endpoints (e.g., one per branch or analyzer).
    The API key authenticates inbound pushes from the LIS; the callback_url
    receives outbound results.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, help_text="Human label, e.g. 'Main Lab Sysmex XN-1000'")
    is_active = models.BooleanField(default=True)

    # What format does the LIS send / expect back?
    inbound_format = models.CharField(
        max_length=20,
        choices=IntegrationFormat.choices,
        default=IntegrationFormat.JSON,
    )
    outbound_format = models.CharField(
        max_length=20,
        choices=IntegrationFormat.choices,
        default=IntegrationFormat.JSON,
    )

    # API key for inbound auth (LIS → Clinomic).
    # Separate from user JWT — this is a machine-to-machine credential.
    api_key = models.CharField(max_length=64, unique=True, db_index=True)

    # Where to push results back to the LIS (optional — omit if LIS polls).
    callback_url = models.URLField(blank=True, default='')
    callback_headers = models.JSONField(
        default=dict, blank=True,
        help_text='Extra HTTP headers for the callback (e.g. {"Authorization": "Bearer xxx"})',
    )

    # Field mapping: maps external LIS field names to Clinomic CBC field names.
    # Default covers the standard CBC parameter names; labs override if their
    # LIS uses different keys (e.g. "HGB" instead of "Hb").
    field_mapping = models.JSONField(
        default=dict, blank=True,
        help_text='{"lis_field": "clinomic_field"} — e.g. {"HGB": "Hb", "WBC_COUNT": "WBC"}',
    )

    # Default patient/lab identifiers used when the inbound message
    # doesn't include them (common with simple CSV/analyzer integrations).
    default_lab_code = models.CharField(max_length=50, blank=True, default='')
    default_doctor_code = models.CharField(max_length=50, blank=True, default='')

    # Auto-approve: if True, the screening result auto-transitions to
    # in_progress after prediction (skips manual review). Useful for
    # high-volume labs with trusted analyzer pipelines.
    auto_approve = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.inbound_format} → {self.outbound_format})"


class IntegrationLog(models.Model):
    """
    Audit log for every inbound/outbound integration event.
    Helps debug mapping errors and proves data provenance for NABL.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    endpoint = models.ForeignKey(IntegrationEndpoint, on_delete=models.CASCADE, related_name='logs')
    direction = models.CharField(max_length=10, choices=[('inbound', 'Inbound'), ('outbound', 'Outbound')])
    status = models.CharField(
        max_length=20,
        choices=[
            ('success', 'Success'),
            ('parse_error', 'Parse Error'),
            ('predict_error', 'Predict Error'),
            ('callback_error', 'Callback Error'),
        ],
    )
    # Store enough to debug but NOT full PHI — just the mapping result + error
    raw_hash = models.CharField(max_length=64, help_text='SHA256 of the raw inbound payload (for dedup/audit)')
    mapped_fields = models.JSONField(default=dict, help_text='CBC fields after mapping (before prediction)')
    error_detail = models.TextField(blank=True, default='')
    screening_id = models.UUIDField(null=True, blank=True, help_text='Resulting Screening UUID if successful')

    # Latency tracking
    duration_ms = models.IntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['endpoint', '-created_at']),
        ]

"""
PHI access audit logging for HIPAA compliance.

Every time Protected Health Information is read or written, call
log_phi_access().  Failures are caught and logged — they must never
interrupt an API response.

The AuditLogEntry table uses a hash chain so that any tampering with
existing rows is detectable.  Each entry's entry_hash covers the
previous hash, making the chain append-only.
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


def log_phi_access(request, patient_id: str, action: str, details: dict | None = None) -> None:
    """
    Append an immutable, HMAC-signed entry to the audit chain.

    Parameters
    ----------
    request:    DRF Request — used to extract actor, IP, and user agent.
    patient_id: The patient_id string (not a DB primary key).
    action:     Short action label, e.g. 'PHI_READ', 'PHI_PREDICT', 'PHI_CONSENT_READ'.
    details:    Optional extra context stored in the JSON details column.
    """
    try:
        _write_audit_entry(request, patient_id, action, details or {})
    except Exception:
        # Audit logging must never crash the API response.
        logger.exception(
            "PHI audit log write failed for patient=%s action=%s", patient_id, action
        )


# ── Internal ──────────────────────────────────────────────────────────────────

def _get_client_ip(request) -> str | None:
    """Return the real client IP, respecting X-Forwarded-For from nginx."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _write_audit_entry(request, patient_id: str, action: str, details: dict) -> None:
    """Core write, wrapped in a DB transaction with row-level lock."""
    from apps.core.models import AuditLogEntry  # local import avoids circular import

    actor = request.user.username if request.user.is_authenticated else 'anonymous'
    ip = _get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:512]
    signing_key = getattr(settings, 'AUDIT_SIGNING_KEY', '') or ''

    with transaction.atomic():
        # Lock the last row so concurrent writers get a consistent sequence.
        last = (
            AuditLogEntry.objects
            .select_for_update()
            .order_by('-sequence')
            .values('sequence', 'entry_hash')
            .first()
        )

        if last:
            sequence = last['sequence'] + 1
            previous_hash = last['entry_hash']
        else:
            sequence = 1
            previous_hash = '0' * 64

        # Canonical representation to hash
        entry_data = json.dumps({
            'sequence': sequence,
            'actor': actor,
            'action': action,
            'entity_type': 'Patient',
            'entity_id': patient_id,
            'previous_hash': previous_hash,
            'details': details,
        }, sort_keys=True)

        entry_hash = hashlib.sha256(entry_data.encode()).hexdigest()

        # HMAC-SHA256 signature over the entry hash
        if signing_key:
            signature = hmac.new(
                signing_key.encode(),
                entry_hash.encode(),
                hashlib.sha256,
            ).hexdigest()
        else:
            signature = 'unsigned'

        AuditLogEntry.objects.create(
            sequence=sequence,
            actor=actor,
            action=action,
            entity_type='Patient',
            entity_id=patient_id,
            details=details,
            previous_hash=previous_hash,
            entry_hash=entry_hash,
            signature=signature,
            ip_address=ip,
            user_agent=user_agent,
        )

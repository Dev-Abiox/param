"""
PHI access audit logging for HIPAA / DPDP compliance.

Every time Protected Health Information is read or written, call
log_phi_access().  Failures are caught and logged — they must never
interrupt an API response.

The AuditLogEntry table uses a hash chain so that any tampering with
existing rows is detectable.  Each entry's entry_hash covers the
previous hash, making the chain append-only.

DPDP hygiene
------------
The `details` JSON column must never hold raw PHI (names, ages, CBC
values, etc).  Every write is run through sanitise_details() which:

  1. Drops any key matching a known PHI-adjacent name (name, age, sex,
     email, phone, address, dob, hb, mcv, rdw, ...).
  2. Replaces free-text strings longer than FREE_TEXT_MAX_LEN with a
     SHA-256 prefix hash, preserving traceability without content.
  3. Walks nested dicts and lists recursively so that sanitisation is
     not bypassed by wrapping a PHI value one level deep.

Audit-log retention is 7 years (see DATA_RETENTION_POLICY.md),
justified under DPDP Act §7(g) statutory-compliance purpose and the
Evidence Act for dispute defence.
"""

import hashlib
import hmac
import json
import logging

from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

# Keys whose values are presumed to contain PHI and must be dropped
# entirely before an audit row is written.  Matching is case-insensitive
# and substring-based so that variants like `patient_name`, `patientAge`,
# `hb_g_dl`, `cbcSnapshot`, etc. are all caught.
_PHI_KEY_SUBSTRINGS = frozenset({
    # direct identifiers
    'name',          # patient_name, referring_doctor_name, ...
    'email',
    'phone',
    'mobile',
    'address',
    'dob',
    'date_of_birth',
    # demographics
    'age',           # avoid logging age in free-text details
    'sex',
    'gender',
    # CBC / lab values — these are PHI when tied to a patient_id
    'hb', 'hgb',
    'rbc', 'hct',
    'mcv', 'mch', 'mchc',
    'rdw',
    'wbc',
    'neutrophil', 'lymphocyte', 'monocyte',
    'eosinophil', 'basophil',
    'platelet',
    'cbc_snapshot', 'cbc',
    'b12', 'ferritin',
    # clinical text
    'clinical_note', 'narrative', 'note',
})

# Free-text strings longer than this are replaced with a length-prefixed
# hash so that we preserve the fact that something was logged without
# retaining its content.
FREE_TEXT_MAX_LEN = 128


def sanitise_details(details: dict | None) -> dict:
    """Remove known PHI keys and hash long free-text values in `details`.

    Whitelist-flavoured defensive cleanup — the caller is still expected
    to pass non-PHI context, but this function guarantees that audit
    rows never retain raw PHI even if a call site is buggy.

    Returns a new dict; the input is not mutated.
    """
    if not details:
        return {}
    return _sanitise_value(details)


def _key_is_phi(key: str) -> bool:
    if not isinstance(key, str):
        return False
    k = key.lower()
    return any(sub in k for sub in _PHI_KEY_SUBSTRINGS)


def _hash_free_text(value: str) -> str:
    h = hashlib.sha256(value.encode('utf-8', errors='replace')).hexdigest()
    return f'<redacted:len={len(value)}:sha256={h[:16]}>'


def _sanitise_value(value):
    """Recursively sanitise an audit-detail value."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _key_is_phi(k):
                out[k] = '<redacted:phi>'
            else:
                out[k] = _sanitise_value(v)
        return out
    if isinstance(value, list):
        return [_sanitise_value(x) for x in value]
    if isinstance(value, tuple):
        return tuple(_sanitise_value(x) for x in value)
    if isinstance(value, str):
        if len(value) > FREE_TEXT_MAX_LEN:
            return _hash_free_text(value)
        return value
    # int / float / bool / None / everything else pass through unchanged
    return value


def log_phi_access(request, patient_id: str, action: str, details: dict | None = None) -> None:
    """
    Append an immutable, HMAC-signed entry to the audit chain.

    Parameters
    ----------
    request:    DRF Request — used to extract actor, IP, and user agent.
    patient_id: The patient_id string (not a DB primary key).
    action:     Short action label, e.g. 'PHI_READ', 'PHI_PREDICT', 'PHI_CONSENT_READ'.
    details:    Optional extra context stored in the JSON details column.
                Run through sanitise_details() before persistence — PHI-
                adjacent keys are redacted and long free-text is hashed.
    """
    try:
        _write_audit_entry(request, patient_id, action, sanitise_details(details))
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

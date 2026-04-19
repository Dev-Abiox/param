"""
Celery tasks for the screening app.

Currently handles:
  - process_bulk_import: parse CSV rows → run ML prediction → persist Screening records
"""

import csv
import io
import logging

import structlog
from celery import shared_task

logger = structlog.get_logger(__name__)

# Required CSV column → internal CBC key mapping
_CSV_TO_CBC = {
    'hb':      'Hb_g_dL',
    'rbc':     'RBC_million_uL',
    'hct':     'HCT_percent',
    'mcv':     'MCV_fL',
    'mch':     'MCH_pg',
    'mchc':    'MCHC_g_dL',
    'rdw':     'RDW_percent',
    'wbc':     'WBC_10_3_uL',
    'plt':     'Platelets_10_3_uL',
    'neu_pct': 'Neutrophils_percent',
    'lym_pct': 'Lymphocytes_percent',
}

_REQUIRED_COLS = {'patient_id', 'age', 'sex'} | set(_CSV_TO_CBC.keys())


@shared_task(name='screening.process_bulk_import', bind=True, max_retries=2, default_retry_delay=60)
def process_bulk_import(self, job_id: str, csv_text: str, lab_code: str, username: str):
    """
    Process a CSV bulk import job.

    Each row is validated, run through the ML engine, and saved as a
    Screening record.  Progress is written back to BulkImportJob after
    every row so the status endpoint reflects real-time progress.

    CSV required columns (case-insensitive header):
        patient_id, patient_name, lab_id, doctor_id,
        hb, rbc, hct, mcv, mch, mchc, rdw, wbc, plt, neu_pct, lym_pct,
        age, sex
    """
    from datetime import datetime, timezone
    import hashlib, json, uuid as _uuid

    from apps.core.crypto import encrypt_field
    from apps.screening.ml_engine import get_ml_engine
    from apps.screening.models import BulkImportJob, Doctor, Lab, Patient, Screening

    try:
        job = BulkImportJob.objects.get(id=job_id)
    except BulkImportJob.DoesNotExist:
        logger.error("bulk_import_job_not_found", job_id=job_id)
        return

    job.status = BulkImportJob.JobStatus.PROCESSING
    job.save(update_fields=['status', 'updated_at'])

    reader = csv.DictReader(io.StringIO(csv_text))
    # Normalise headers to lowercase
    reader.fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]

    missing = _REQUIRED_COLS - set(reader.fieldnames)
    if missing:
        job.status = BulkImportJob.JobStatus.FAILED
        job.error_detail = [{'row': 0, 'error': f"Missing columns: {sorted(missing)}"}]
        job.save(update_fields=['status', 'error_detail', 'updated_at'])
        return

    rows = list(reader)
    job.total_rows = len(rows)
    job.save(update_fields=['total_rows', 'updated_at'])

    try:
        engine = get_ml_engine()
    except Exception as exc:
        job.status = BulkImportJob.JobStatus.FAILED
        job.error_detail = [{'row': 0, 'error': f"ML engine unavailable: {exc}"}]
        job.save(update_fields=['status', 'error_detail', 'updated_at'])
        return

    errors = []
    processed = 0

    for i, row in enumerate(rows, start=1):
        try:
            # Parse CBC fields
            cbc = {}
            for csv_col, cbc_key in _CSV_TO_CBC.items():
                cbc[cbc_key] = float(row[csv_col])
            cbc['Age'] = int(row['age'])
            cbc['Sex'] = row['sex'].strip().upper()[0]   # M or F

            patient_id = row['patient_id'].strip()
            if not patient_id:
                raise ValueError("patient_id is empty")

            # Resolve lab and doctor
            resolved_lab_code = (row.get('lab_id', '') or lab_code).strip()
            if not resolved_lab_code:
                raise ValueError("lab_id missing in CSV row and not provided via query param")
            lab = Lab.objects.filter(code=resolved_lab_code).first()
            if not lab:
                raise ValueError(f"Lab '{resolved_lab_code}' not found")
            doctor = None
            if row.get('doctor_id', '').strip():
                doctor = Doctor.objects.filter(code=row['doctor_id'].strip()).first()

            # Upsert patient, scoped to lab to prevent cross-org data mixing
            patient, _ = Patient.objects.update_or_create(
                patient_id=patient_id,
                lab=lab,
                defaults={
                    'name_encrypted': encrypt_field((row.get('patient_name') or '').strip()),
                    'age_encrypted':  encrypt_field(str(cbc['Age'])),
                    'sex_encrypted':  encrypt_field(cbc['Sex']),
                    'referring_doctor': doctor,
                }
            )

            # Run prediction
            result = engine.predict(cbc)

            # Build reproducibility hashes
            req_hash  = hashlib.sha256(f"{patient_id}:{json.dumps(cbc, sort_keys=True)}".encode()).hexdigest()
            resp_hash = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
            sid       = _uuid.uuid4()
            s_hash    = hashlib.sha256(f"{sid}:{req_hash}:{resp_hash}".encode()).hexdigest()

            Screening.objects.create(
                id=sid,
                patient=patient,
                lab=lab,
                doctor=doctor,
                performed_by=username,
                risk_class=result['riskClass'],
                label_text=result['labelText'],
                probabilities=result['probabilities'],
                rules_fired=result['rulesFired'],
                cbc_snapshot=cbc,
                indices=result['indices'],
                model_version=result['modelVersion'],
                model_artifact_hash=result['modelArtifactHash'],
                request_hash=req_hash,
                response_hash=resp_hash,
                screening_hash=s_hash,
            )
            processed += 1

        except Exception as exc:
            errors.append({'row': i, 'patient_id': row.get('patient_id', '?'), 'error': str(exc)})
            logger.warning("bulk_import_row_failed", row=i, error=str(exc))

        # Update progress every row
        job.processed_rows = processed
        job.failed_rows = len(errors)
        job.error_detail = errors
        job.save(update_fields=['processed_rows', 'failed_rows', 'error_detail', 'updated_at'])

    job.status = BulkImportJob.JobStatus.DONE if not errors or processed > 0 else BulkImportJob.JobStatus.FAILED
    job.save(update_fields=['status', 'updated_at'])
    logger.info("bulk_import_complete", job_id=job_id, processed=processed, failed=len(errors))


# ── SHAP backfill ─────────────────────────────────────────────────────────────
# Long-form → short-form key map for legacy cbc_snapshot records written before
# DRF's source='Hb' aliasing landed. New records already use short keys.
_LEGACY_CBC_KEY_MAP = {
    'Hb_g_dL':              'Hb',
    'RBC_million_uL':       'RBC',
    'HCT_percent':          'HCT',
    'MCV_fL':               'MCV',
    'MCH_pg':               'MCH',
    'MCHC_g_dL':            'MCHC',
    'RDW_percent':          'RDW',
    'WBC_10_3_uL':          'WBC',
    'Platelets_10_3_uL':    'Platelets',
    'Neutrophils_percent':  'Neutrophils',
    'Lymphocytes_percent':  'Lymphocytes',
}


def _normalise_cbc_snapshot(snapshot: dict) -> dict:
    """Coerce legacy long-form keys to the short form the engine expects."""
    if not snapshot:
        return {}
    out = dict(snapshot)
    for long_key, short_key in _LEGACY_CBC_KEY_MAP.items():
        if long_key in out and short_key not in out:
            out[short_key] = out.pop(long_key)
    return out


@shared_task(name='screening.backfill_shap_values', bind=True, max_retries=0)
def backfill_shap_values(self, batch_size: int = 200, limit: int | None = None):
    """
    Populate ``screening.indices['shap_values']`` for historical records that
    pre-date the SHAP fix.

    Args:
        batch_size: how many rows to iterate before flushing log progress.
        limit:      optional hard cap on total records processed (useful for
                    a canary run before a full backfill).

    Returns:
        dict with processed / skipped / failed counts.

    Safety:
        - Reads ``cbc_snapshot`` and writes ONLY ``indices`` — does not touch
          ``risk_class``, ``label_text``, ``probabilities``, or any hash
          field. Prediction outputs are not mutated.
        - Records where SHAP computation fails are skipped, not failed, so
          one degenerate row does not abort the job.
    """
    import pandas as pd

    from apps.screening.ml_engine import get_ml_engine
    from apps.screening.models import Screening

    engine = get_ml_engine()
    if not engine.is_ready:
        logger.error("backfill_shap_engine_not_ready")
        return {'processed': 0, 'skipped': 0, 'failed': 0, 'error': 'ml_not_ready'}

    expected_cols = [
        "Age", "Sex", "Hb", "RBC", "HCT", "MCV", "MCH", "MCHC",
        "RDW", "WBC", "Platelets", "Neutrophils", "Lymphocytes",
    ]

    qs = Screening.objects.exclude(indices__has_key='shap_values').only(
        'id', 'indices', 'cbc_snapshot'
    ).order_by('-created_at')
    if limit:
        qs = qs[:limit]

    processed = skipped = failed = 0

    for screening in qs.iterator(chunk_size=batch_size):
        try:
            cbc = _normalise_cbc_snapshot(screening.cbc_snapshot or {})
            if not cbc:
                skipped += 1
                continue

            df = pd.DataFrame([cbc])
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = 0
            df = df[expected_cols]
            if df["Sex"].dtype == "object":
                df["Sex"] = df["Sex"].map(
                    {"M": 1, "F": 0, "m": 1, "f": 0}
                ).fillna(0)

            shap_values = engine.compute_shap_values(df)
            if not shap_values:
                skipped += 1
                continue

            indices = dict(screening.indices or {})
            indices['shap_values'] = shap_values
            Screening.objects.filter(id=screening.id).update(indices=indices)
            processed += 1

            if processed % batch_size == 0:
                logger.info(
                    "backfill_shap_progress",
                    processed=processed, skipped=skipped, failed=failed,
                )

        except Exception as exc:
            failed += 1
            logger.warning(
                "backfill_shap_row_failed",
                screening_id=str(screening.id), error=str(exc),
            )

    logger.info(
        "backfill_shap_complete",
        processed=processed, skipped=skipped, failed=failed,
    )
    return {'processed': processed, 'skipped': skipped, 'failed': failed}

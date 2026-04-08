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

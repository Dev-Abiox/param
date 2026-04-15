"""
Celery tasks for data retention, housekeeping, and backup.

Schedule is defined in settings.CELERY_BEAT_SCHEDULE.

Retention policy (HIPAA §164.530(j)):
  - Screening / Consent records: DATA_RETENTION_DAYS (default 2555 = 7 years)
  - RefreshToken records: deleted as soon as they expire (daily cleanup)
  - AuditLogEntry: never deleted (immutable compliance record)
"""

import gzip
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone

import structlog
from celery import shared_task
from django.conf import settings

logger = structlog.get_logger(__name__)


@shared_task(name='core.purge_expired_refresh_tokens')
def purge_expired_refresh_tokens() -> int:
    """
    Delete JWT refresh tokens that have already expired.

    Runs hourly.  Keeps the refresh_tokens table small so token-lookup
    queries stay fast.
    """
    from apps.core.models import RefreshToken

    now = datetime.now(timezone.utc)
    deleted, _ = RefreshToken.objects.filter(expires_at__lt=now).delete()
    logger.info("retention_purge", entity="refresh_tokens", deleted=deleted)
    return deleted


@shared_task(name='core.purge_old_screenings')
def purge_old_screenings() -> int:
    """
    Delete Screening records older than DATA_RETENTION_DAYS.

    Default is 2555 days (7 years) per HIPAA minimum.  Runs daily at 02:00 UTC.
    The associated Patient record is NOT deleted — it may be referenced by
    other screenings still within the retention window.

    Iterates all tenant schemas because Screening is a tenant-specific model.
    """
    from apps.core.models import Organization
    from apps.screening.models import Screening
    from django_tenants.utils import schema_context

    retention_days = getattr(settings, 'DATA_RETENTION_DAYS', 2555)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    total_deleted = 0

    for org in Organization.objects.exclude(schema_name='public'):
        with schema_context(org.schema_name):
            deleted, _ = Screening.objects.filter(created_at__lt=cutoff).delete()
            if deleted:
                logger.info("retention_purge", entity="screenings", deleted=deleted,
                            retention_days=retention_days, schema=org.schema_name)
                total_deleted += deleted

    return total_deleted


@shared_task(name='core.expire_stale_consents')
def expire_stale_consents() -> int:
    """
    Transition active consents whose expires_at has passed to 'expired' status.
    Runs hourly so the GET endpoint never needs to mutate state.

    Iterates all tenant schemas because Consent is a tenant-specific model.
    """
    from apps.core.models import Organization
    from apps.screening.models import Consent
    from django_tenants.utils import schema_context

    now = datetime.now(timezone.utc)
    total_updated = 0

    for org in Organization.objects.exclude(schema_name='public'):
        with schema_context(org.schema_name):
            updated = Consent.objects.filter(
                status='active',
                expires_at__lt=now,
            ).update(status='expired')
            if updated:
                logger.info("consents_expired", count=updated, schema=org.schema_name)
                total_updated += updated

    return total_updated


@shared_task(name='core.purge_old_consents')
def purge_old_consents() -> int:
    """
    Delete Consent records that are both non-active AND older than
    DATA_RETENTION_DAYS.  Active consents are never deleted.

    Runs daily at 02:00 UTC alongside purge_old_screenings.
    Iterates all tenant schemas because Consent is a tenant-specific model.
    """
    from apps.core.models import Organization
    from apps.screening.models import Consent
    from django_tenants.utils import schema_context

    retention_days = getattr(settings, 'DATA_RETENTION_DAYS', 2555)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    total_deleted = 0

    for org in Organization.objects.exclude(schema_name='public'):
        with schema_context(org.schema_name):
            deleted, _ = Consent.objects.filter(
                status__in=['revoked', 'expired'],
                updated_at__lt=cutoff,
            ).delete()
            if deleted:
                logger.info("retention_purge", entity="consents", deleted=deleted,
                            retention_days=retention_days, schema=org.schema_name)
                total_deleted += deleted

    return total_deleted


@shared_task(name='core.backup_database', bind=True, max_retries=2)
def backup_database(self) -> str:
    """
    Dump the PostgreSQL database with pg_dump, gzip-compress it, and upload
    the archive to S3.

    Only runs when BACKUP_S3_BUCKET is configured.  Fires daily at 03:00 UTC
    (schedule in settings.CELERY_BEAT_SCHEDULE).

    Returns the S3 object key on success, or 'skipped' if S3 is not
    configured.
    """
    bucket = getattr(settings, 'BACKUP_S3_BUCKET', '')
    if not bucket:
        logger.info("backup_skipped", reason="BACKUP_S3_BUCKET not configured")
        return 'skipped'

    db = settings.DATABASES['default']
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    prefix = getattr(settings, 'BACKUP_S3_PREFIX', 'db-backups/')
    s3_key = f"{prefix}{timestamp}.dump.gz"

    env = {
        **os.environ,
        'PGPASSWORD': db.get('PASSWORD', ''),
    }

    pg_dump_cmd = [
        'pg_dump',
        '--format=custom',
        '--no-owner',
        '--no-acl',
        f"--host={db.get('HOST', 'localhost')}",
        f"--port={db.get('PORT', '5432')}",
        f"--username={db.get('USER', 'postgres')}",
        db.get('NAME', 'clinomic'),
    ]

    try:
        with tempfile.NamedTemporaryFile(suffix='.dump.gz', delete=False) as tmp:
            tmp_path = tmp.name

        # Run pg_dump and pipe through gzip
        with gzip.open(tmp_path, 'wb') as gz_fh:
            result = subprocess.run(
                pg_dump_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=True,
            )
            gz_fh.write(result.stdout)

        # Upload to S3
        import boto3
        s3 = boto3.client(
            's3',
            aws_access_key_id=getattr(settings, 'AWS_BACKUP_ACCESS_KEY_ID', None),
            aws_secret_access_key=getattr(settings, 'AWS_BACKUP_SECRET_ACCESS_KEY', None),
        )
        s3.upload_file(tmp_path, bucket, s3_key)

        # Report success to Prometheus. The BackupMissing alert watches this
        # gauge via (time() - clinomic_backup_last_success_timestamp) > 25h.
        try:
            import time as _time
            from apps.core.metrics import BACKUP_LAST_SUCCESS_TIMESTAMP
            BACKUP_LAST_SUCCESS_TIMESTAMP.set(_time.time())
        except Exception:
            # Metric failures must never break a completed backup.
            pass

        logger.info("backup_complete", s3_bucket=bucket, s3_key=s3_key)
        return s3_key

    except subprocess.CalledProcessError as exc:
        logger.error("backup_pg_dump_failed", stderr=exc.stderr.decode()[:500])
        raise self.retry(exc=exc, countdown=300)
    except Exception as exc:
        logger.error("backup_upload_failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

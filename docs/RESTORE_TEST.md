# Database Restore Drill

A backup you haven't restored is not a backup. Run this drill **before launch** and **monthly** thereafter. Budget: 20 minutes on a running production host.

This drill is deliberately safe: it restores into a **scratch database on the same Postgres container**, never touches the live `clinomic` database, and cleans up after itself.

---

## What this proves

If this drill succeeds, you have verified end-to-end that:

1. The daily `core.backup_database` Celery task is actually producing S3 artifacts
2. The S3 credentials in `.env` can read those artifacts
3. The `pg_dump --format=custom` archive is structurally valid
4. `pg_restore` can rebuild the schemas and data from it
5. The `clinomic_backup_last_success_timestamp` Prometheus gauge is being updated

If any of these fail, the `BackupMissing` alert is masking a real problem.

---

## Prerequisites

On the prod VM:

```bash
ssh deploy@66.116.225.67
cd /opt/clinomic-b12-platform

# Confirm BACKUP_S3_BUCKET is set
grep BACKUP_S3_BUCKET .env
```

If `BACKUP_S3_BUCKET` is empty, **stop here**. Set it + `AWS_BACKUP_ACCESS_KEY_ID` + `AWS_BACKUP_SECRET_ACCESS_KEY` in `.env`, then restart the `backend` and `celery_worker` containers. Trigger one manual backup to populate S3:

```bash
docker compose -f docker-compose.prod.yml exec celery_worker \
  celery -A clinomic call core.backup_database
```

Wait ~2 minutes, then continue.

---

## The drill

```bash
cd /opt/clinomic-b12-platform
bash scripts/restore_test.sh
```

Expected output:

```
[1/6] Listing most recent backup in S3 ...
      s3://<bucket>/db-backups/20260415T030001Z.dump.gz
[2/6] Downloading to /tmp/clinomic_restore_test.dump.gz ...
      OK (<size> MB)
[3/6] Gunzipping ...
      OK (<size> MB uncompressed)
[4/6] Creating scratch database `clinomic_restore_test` ...
      CREATE DATABASE
[5/6] pg_restore into scratch ...
      OK — N relations restored, M rows
[6/6] Sanity queries ...
      screenings:   <count>
      users:        <count>
      organizations: <count>
      latest screening: <timestamp>
Cleaning up scratch DB ...
      DROP DATABASE
Restore drill PASSED.
```

**If the drill fails at any step**, the output explains what and where. The scratch database is always torn down at the end even on partial failure (the script uses `trap` on EXIT).

---

## What to record

After each successful drill, log it in `docs/INCIDENTS/backup-drills.md` (create if missing):

```markdown
# Backup restore drills

| Date       | Operator | S3 object restored           | Row counts (screenings / users / orgs) | Notes |
|------------|----------|------------------------------|----------------------------------------|-------|
| 2026-04-15 | @param   | 20260415T030001Z.dump.gz     | 138 / 12 / 4                          | First drill, passed |
```

If the drill ever fails in production, that's a ship-blocker — write an incident note.

---

## What this drill does NOT prove

- That your backup retention is long enough (we keep `--storage.tsdb.retention.time=30d` on Prometheus but S3 lifecycle is separately configured on the bucket — check it)
- That restoring into a **fresh empty host** works (recovery from total VM loss). For that, do the disaster-recovery drill: spin up a new VM, install Docker, pull the backup from S3 by hand, restore, and point a scratch DNS at it. Budget: 2 hours. Do this at least once, before the first billing cycle closes.
- That your S3 bucket is configured with versioning + MFA-delete + cross-region replication. Check bucket settings separately.

# Backup Setup — Cloudflare R2 (recommended, free)

Your DB is ~19 MB right now. Cloudflare R2's free tier gives you **10 GB storage + zero egress fees**, which covers you for months even as you grow. R2 speaks the S3 API, so the existing backup task works with one extra env var.

If you don't want to use R2, any S3-compatible store works — this doc covers R2 in detail and B2 / DigitalOcean Spaces in the "alternatives" section. A zero-cost local-snapshot fallback is at the end.

---

## Option A — Cloudflare R2 (recommended)

### 1. Create the bucket

1. Go to https://dash.cloudflare.com and sign in (free account is fine)
2. Left sidebar → **R2 Object Storage**
3. First time only: click **Purchase R2** — you must add a payment method but the free tier (10 GB, 1M Class A ops, 10M Class B ops) is truly free; you won't be charged unless you cross those limits
4. Click **Create bucket**
   - Name: `clinomic-backups`
   - Location: `Automatic` (fine) or pick a specific region
   - Storage class: `Standard`
5. Click **Create bucket**

Note your **Account ID** — it's shown on the R2 overview page, format like `a1b2c3d4e5f6...`.

### 2. Create an API token

1. R2 → sidebar → **Manage R2 API Tokens** (or **API** tab at the top)
2. Click **Create API Token**
3. Token name: `clinomic-backup`
4. Permissions: **Object Read & Write**
5. Specify bucket: `clinomic-backups` (don't grant account-wide)
6. TTL: leave blank (no expiry) or set a date if you want rotation
7. Click **Create API Token**
8. **Copy the `Access Key ID` and `Secret Access Key` now** — the secret is shown only once

### 3. Set the env vars on the VM

```bash
ssh deploy@66.116.225.67
cd /opt/clinomic-b12-platform
vim .env
```

Add these lines (replace `<account-id>` with your Cloudflare account ID and the keys from step 2):

```env
BACKUP_S3_BUCKET=clinomic-backups
BACKUP_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
BACKUP_S3_REGION=auto
AWS_BACKUP_ACCESS_KEY_ID=<access-key-id-from-step-2>
AWS_BACKUP_SECRET_ACCESS_KEY=<secret-key-from-step-2>
```

`chmod 600 .env` if it isn't already.

### 4. Recreate affected containers

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate backend celery_worker celery_beat
```

`backend` and both Celery containers need the new env. The backup itself runs in `celery_worker` (not `celery_email_worker`) because the beat schedule routes `core.backup_database` to the default queue.

### 5. Manually trigger a backup to prove it works

```bash
docker compose -f docker-compose.prod.yml exec celery_worker \
  celery -A clinomic call core.backup_database
```

This returns a task ID immediately. Wait ~30 seconds, then check the logs:

```bash
docker compose -f docker-compose.prod.yml logs --tail 50 celery_worker | grep -E "backup_"
```

You want to see `backup_complete` with an `s3_key` like `db-backups/20260415T123045Z.dump.gz`. If you see `backup_pg_dump_failed` or `backup_upload_failed`, the log line includes the error — most common causes are wrong endpoint URL (forgot `https://`), wrong account ID, or wrong bucket name.

### 6. Verify the object is actually in R2

In the Cloudflare dashboard: R2 → `clinomic-backups` → you should see a file like `db-backups/20260415T123045Z.dump.gz`.

### 7. Verify the Prometheus gauge populated

```bash
curl -s 'http://localhost:9090/api/v1/query?query=clinomic_backup_last_success_timestamp' | python3 -m json.tool
```

You should see a `value` with a recent Unix timestamp. Within ~1 minute the `BackupMissing` alert in Prometheus should transition from `pending` → `inactive`.

### 8. Run the restore drill

```bash
cd /opt/clinomic-b12-platform
bash scripts/restore_test.sh
```

This restores the backup you just created into a scratch database, runs sanity queries, and drops the scratch DB. If it prints **`Restore drill PASSED`** you're good to go.

### 9. Let the scheduled task take over

The daily backup runs at **03:00 UTC** via Celery beat. Tomorrow morning, check again:

```bash
docker compose -f docker-compose.prod.yml logs --since 26h celery_worker | grep backup_complete
```

You should see one entry per day, and the `BackupMissing` alert stays `inactive`.

---

## Option B — Backblaze B2

Same env vars, different endpoint. B2 has 10 GB free tier, $6/TB after that.

1. Sign up at https://www.backblaze.com/sign-up/cloud-storage
2. Create a **private bucket** named `clinomic-backups`
3. Generate an **Application Key** scoped to that bucket with read+write
4. In `.env`:

```env
BACKUP_S3_BUCKET=clinomic-backups
BACKUP_S3_ENDPOINT_URL=https://s3.<region>.backblazeb2.com
BACKUP_S3_REGION=<region>
AWS_BACKUP_ACCESS_KEY_ID=<keyID>
AWS_BACKUP_SECRET_ACCESS_KEY=<applicationKey>
```

Region is shown on the bucket page, typically `us-east-005`, `eu-central-003`, etc.

5. Same recreate + trigger + verify steps as Option A.

---

## Option C — DigitalOcean Spaces

Not free ($5/mo for 250 GB starter), but simple if you already use DO.

```env
BACKUP_S3_BUCKET=clinomic-backups
BACKUP_S3_ENDPOINT_URL=https://<region>.digitaloceanspaces.com
BACKUP_S3_REGION=<region>
AWS_BACKUP_ACCESS_KEY_ID=<spaces-key>
AWS_BACKUP_SECRET_ACCESS_KEY=<spaces-secret>
```

Region is one of `nyc3`, `sfo3`, `ams3`, `sgp1`, `fra1`.

---

## Zero-cost fallback — local snapshot on the same VM

**Warning:** This is NOT offsite. If the VM disk dies, the backup dies with it. It's strictly a "better than nothing" option until you can set up R2. Do not rely on this for HIPAA-grade retention.

### How it works

You keep the existing `core.backup_database` task but run it without S3 credentials — then separately rsync the `postgres_data` volume to a timestamped directory on the host disk via a cron job.

```bash
# On the VM
ssh deploy@66.116.225.67
sudo mkdir -p /opt/backups
sudo chown deploy:deploy /opt/backups
```

Add this script as `/opt/clinomic-b12-platform/scripts/local_backup.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/opt/backups"
DATE=$(date -u +%Y%m%dT%H%M%SZ)
OUT="${BACKUP_DIR}/clinomic-${DATE}.dump.gz"

cd /opt/clinomic-b12-platform
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U postgres --format=custom --no-owner --no-acl clinomic \
  | gzip > "$OUT"

# Keep only the last 14 days
find "$BACKUP_DIR" -name "clinomic-*.dump.gz" -mtime +14 -delete

echo "wrote $OUT ($(du -h $OUT | awk '{print $1}'))"
```

```bash
chmod +x scripts/local_backup.sh

# Run it manually first to confirm it works
bash scripts/local_backup.sh
ls -lh /opt/backups/
```

Schedule it via cron (on the VM, not Celery — this is a safety net that must run even if Django is broken):

```bash
sudo crontab -e
```

Add:

```cron
# Local DB backup — safety net when offsite S3 isn't configured
15 3 * * * cd /opt/clinomic-b12-platform && /bin/bash scripts/local_backup.sh >> /var/log/clinomic-backup.log 2>&1
```

**Important caveats:**
- This does NOT update `clinomic_backup_last_success_timestamp`, so the Prometheus `BackupMissing` alert will still fire — that's correct, because you still lack offsite backup. Silence the alert only temporarily (`amtool silence add alertname=BackupMissing --duration=168h --comment="local fallback; R2 coming"`).
- If you forget to set up R2 and the VM dies, you lose everything — the alert is there to nag you.
- Treat this as a 1-week bridge. Set up R2 this week.

---

## Troubleshooting

### `backup_upload_failed: SignatureDoesNotMatch`
Wrong secret key or the clock on the VM is skewed. `timedatectl status` should show NTP in sync. If not, `sudo systemctl restart systemd-timesyncd`.

### `backup_upload_failed: NoSuchBucket`
Bucket name is wrong or the API token was scoped to a different bucket. Double-check both.

### `backup_upload_failed: EndpointConnectionError`
Endpoint URL is wrong or missing `https://`. R2 endpoint is exactly `https://<account-id>.r2.cloudflarestorage.com` — no region segment, no bucket in the path.

### `backup_pg_dump_failed`
Not an S3 issue — `pg_dump` itself failed. Check the `stderr` in the log line. Usually means Postgres is unhealthy or the container is OOMing.

### Gauge stays absent after a manual trigger
The task ran but the `BACKUP_LAST_SUCCESS_TIMESTAMP.set()` line didn't execute, which means `backup_upload_failed` was raised before reaching it. Grep the celery_worker logs for the actual error.

### `BackupMissing` alert fires even after a successful backup
The gauge is per-process, not per-container. If `celery_worker` restarted after the backup ran, the gauge is gone until the next backup. A single daily backup is enough — the alert has a 25-hour grace period. If you want belt-and-suspenders, trigger a second backup right after restart.

---

## What this protects against

| Failure mode | Offsite (R2/B2) | Local snapshot |
|---|---|---|
| Accidental `DROP TABLE` | ✅ restore from yesterday | ✅ |
| Buggy migration destroys data | ✅ | ✅ |
| VM disk corruption | ✅ | ❌ |
| VM deleted / provider outage | ✅ | ❌ |
| Ransomware that encrypts the host | ✅ (if R2 versioning enabled) | ❌ |
| Fat-finger `docker compose down -v` | ✅ | ✅ |

---

## Next steps after this works

1. **Enable R2 bucket versioning** for ransomware protection: R2 dashboard → bucket → Settings → Object versioning → Enable. Free but counts against storage quota.
2. **Set a lifecycle rule** to auto-delete backups older than 90 days (optional; keeps costs bounded as DB grows).
3. **Monthly restore drill** — add a calendar reminder to run `bash scripts/restore_test.sh` and log the result in `docs/INCIDENTS/backup-drills.md`.
4. **When you cross ~100 tenants or ~10 GB backup size**, revisit: R2's 10 GB free tier ends and you start paying $0.015/GB-month. At that point you're a real business and the cost is trivial, but plan for it.

# Production Runbook — Clinomic B12 Screening SaaS

This is the on-call reference for production incidents. Goal: whoever gets paged at 2am can triage, mitigate, and roll back without reading source code.

**Production host:** `66.116.225.67` (BigRock VPS, Ubuntu 22.04, 4 vCPU / 8 GB RAM / 200 GB disk)
**Project path on host:** `/opt/clinomic-b12-platform/`
**Production URL:** `https://clinomiclabs.com`
**Grafana:** `https://clinomiclabs.com/grafana/` (admin password in `.env` on host)
**Status page for on-call:** *(set up UptimeRobot pointing at `/api/health/live` — see "Gaps" at end)*

---

## 1. SSH access

```bash
ssh deploy@66.116.225.67        # primary (deploy user — use this)
ssh root@66.116.225.67          # only when deploy lacks privilege (rare)
```

SSH keys are managed via the GitHub Actions workflow (`secrets.SSH_PRIVATE_KEY`). The server advertises only `ssh-rsa` host keys — if your client is modern and rejects them, add:

```
Host 66.116.225.67
    HostKeyAlgorithms +ssh-rsa
    PubkeyAcceptedAlgorithms +ssh-rsa
```

to `~/.ssh/config`.

Once in, all commands assume you are in `/opt/clinomic-b12-platform/`:

```bash
cd /opt/clinomic-b12-platform
```

---

## 2. The first 60 seconds

When you get a Discord alert, run these in order:

```bash
# 1. Is the site up from outside?
curl -skI https://clinomiclabs.com/api/health/live

# 2. Which containers are unhealthy?
docker compose -f docker-compose.prod.yml ps

# 3. What's the host under?
uptime                         # load average
free -h                        # memory
df -h /                        # disk

# 4. Tail the backend log (last 100 lines)
docker compose -f docker-compose.prod.yml logs --tail 100 backend
```

If `curl` returns 200 and all containers are `Up (healthy)`: the alert is false-positive OR the problem is upstream (DNS/TLS/Cloudflare). Check Grafana and alertmanager directly before poking containers.

---

## 3. Service topology (what depends on what)

```
Internet → nginx → backend (uvicorn×4) → pgbouncer → db (postgres 15)
                    │                  │
                    │                  └── redis (cache + celery broker + channels)
                    │
                    ├── celery_worker        (default, webhooks, alerts queues)
                    ├── celery_email_worker  (email queue only, concurrency=4)
                    └── celery_beat          (scheduled tasks)

Monitoring plane (same host, isolated failure domain):
  prometheus (scrapes backend:8000/metrics) → alertmanager → Discord webhook
  grafana    (reads prometheus) exposed at /grafana/
```

**Key fact:** monitoring lives on the same VM it monitors. If the whole VM dies, no alert escapes. External uptime pinger is mandatory (see gaps).

---

## 4. Common operations

### 4.1 Read logs for one service

```bash
docker compose -f docker-compose.prod.yml logs --tail 200 <service>
docker compose -f docker-compose.prod.yml logs -f <service>     # follow
docker compose -f docker-compose.prod.yml logs --since 10m <service>
```

Services: `backend`, `frontend`, `nginx`, `db`, `pgbouncer`, `redis`, `celery_worker`, `celery_email_worker`, `celery_beat`, `prometheus`, `grafana`, `alertmanager`.

### 4.2 Restart one service without a full redeploy

```bash
docker compose -f docker-compose.prod.yml restart <service>
```

A full-stack restart is `docker compose -f docker-compose.prod.yml up -d --force-recreate`, but you should almost never need that — restart the single offending container.

### 4.3 Check DB connection pool

```bash
# Active connections in Postgres
docker compose -f docker-compose.prod.yml exec db \
  psql -U postgres -d clinomic -c "SELECT state, count(*) FROM pg_stat_activity WHERE datname='clinomic' GROUP BY state;"

# PgBouncer pool view (shows client/server side separately)
docker compose -f docker-compose.prod.yml exec pgbouncer \
  psql -h 127.0.0.1 -p 5432 -U postgres pgbouncer -c "SHOW POOLS;"
```

If `SHOW POOLS` shows `cl_waiting > 0` for more than a few seconds, you're saturating `DEFAULT_POOL_SIZE` (currently 40). Bump it in `docker-compose.prod.yml` and recreate pgbouncer.

### 4.4 Check Celery queue depth

```bash
# Direct Redis inspection (fastest)
docker compose -f docker-compose.prod.yml exec redis \
  redis-cli -a "$REDIS_PASSWORD" LLEN default
# Repeat for: webhooks, alerts, email

# Or via Celery inspect
docker compose -f docker-compose.prod.yml exec celery_worker \
  celery -A clinomic inspect active_queues
```

Queue depths > 1000 on `default` or `email` are the first signal of a worker stall. Restart the relevant worker.

### 4.5 Silence a Prometheus alert during maintenance

```bash
# Enter alertmanager container
docker compose -f docker-compose.prod.yml exec alertmanager \
  amtool silence add alertname=HighPredictLatency --duration=1h --comment="deploy in progress"

# List active silences
docker compose -f docker-compose.prod.yml exec alertmanager amtool silence query

# Remove a silence
docker compose -f docker-compose.prod.yml exec alertmanager amtool silence expire <silence-id>
```

### 4.6 Check what commit is running in prod

```bash
docker inspect clinomic-b12-platform-backend-1 \
  --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'
# Or:
docker compose -f docker-compose.prod.yml images backend
```

The image tag is the git SHA of the commit that built it.

---

## 5. Rollback procedure

**Auto-rollback:** The GitHub Actions deploy job will auto-roll-back to the previous tag if migrations or the `/api/health/live` check fails *during* deploy. You do not need to do anything.

**Manual rollback** (bad deploy passed healthcheck but broke something 10 minutes later):

```bash
# 1. Find the previous SHA. On the VM:
ssh deploy@66.116.225.67
cd /opt/clinomic-b12-platform
docker images ghcr.io/dev-abiox/param --format '{{.Tag}} {{.CreatedAt}}' | head -5

# 2. Pick the SHA immediately before the current one, then:
BACKEND_TAG=<prev_sha> FRONTEND_TAG=<prev_sha> \
  docker compose -f docker-compose.prod.yml up -d --force-recreate backend frontend

# 3. Verify:
curl -skI https://clinomiclabs.com/api/health/live
docker compose -f docker-compose.prod.yml logs --tail 50 backend
```

**After a manual rollback:** revert the bad commit on GitHub (`git revert <sha>` → PR → merge). CI will re-deploy the revert, bringing `:latest` back in sync with what's actually running.

**Database migration rollback:** Django does not auto-reverse migrations. If a migration broke something, you need to:

1. Find the last-known-good SHA (via `git log` on master)
2. Re-deploy that SHA **manually** as above
3. Run `docker compose exec backend python manage.py migrate_schemas <app> <prev_migration_name>` — only if the migration is reversible
4. If not reversible: restore from the latest S3 backup (see §6) and accept data loss back to the backup window

---

## 6. Backup and restore

### 6.1 How backups work

- **Task:** `core.backup_database` in [backend_v3/apps/core/tasks.py](../backend_v3/apps/core/tasks.py)
- **Schedule:** daily at 03:00 UTC via Celery beat (`settings.CELERY_BEAT_SCHEDULE`)
- **Flow:** `pg_dump --format=custom` → gzip → `s3.upload_file()` → `clinomic_backup_last_success_timestamp` gauge set
- **Skipped when:** `BACKUP_S3_BUCKET` env var is empty (task logs `backup_skipped` and returns)

### 6.2 How to verify backups are running

```bash
# Did the task run in the last 24h?
docker compose -f docker-compose.prod.yml logs --since 26h celery_worker | grep backup_

# Is the Prometheus gauge fresh?
curl -s http://localhost:9090/api/v1/query?query=clinomic_backup_last_success_timestamp \
  | python3 -c 'import sys,json,time; v=float(json.load(sys.stdin)["data"]["result"][0]["value"][1]); print(f"age: {(time.time()-v)/3600:.1f}h ago")'
```

The `BackupMissing` alert fires if either: the gauge is absent, or it's older than 25 hours.

### 6.3 Restore drill

See [RESTORE_TEST.md](RESTORE_TEST.md). **Run this at least once before launch** and at least monthly thereafter.

---

## 7. Per-alert playbooks

### 7.1 HighPredictLatency

**Means:** `/api/screening/predict` p95 > 1s for 10 minutes.

1. `docker stats clinomic-b12-platform-backend-1` — CPU/mem under pressure?
2. `docker compose logs --tail 100 backend | grep -E "predict|ml_engine"` — any slow queries or ML errors?
3. `docker compose exec db psql -U postgres -d clinomic -c "SELECT pid, query_start, state, query FROM pg_stat_activity WHERE state != 'idle' AND datname='clinomic' ORDER BY query_start LIMIT 10;"` — long-running DB query?
4. Check Grafana → Predict panel → drill into `outcome` label. If `ml_not_ready` spikes, the model files are unreadable — check the `/app/ml/models` bind mount.

**Mitigation:** `docker compose restart backend` usually clears a memory-leak-induced slowdown. If latency persists after restart, check disk I/O (`iostat -x 1`) — the v1 CatBoost model files are small but volume mount issues have bitten us before.

### 7.2 PredictErrorSpike

**Means:** More than 10% of predict calls returning `error` or `ml_not_ready` over 5 minutes. **Critical** — clinical workflow is broken.

1. Check Sentry for the stack trace (if `SENTRY_DSN` is set).
2. `docker compose logs --tail 200 backend | grep -iE "error|traceback|ml_not_ready"` — what's the exception?
3. If `ml_not_ready`: the ML engine failed to load models. `curl -s http://localhost:8000/api/health/ready` returns the engine status including the canonical hash and load error.
4. If generic `error`: likely DB or Redis. Check `db` and `redis` health + `docker logs`.

**Mitigation:** Backend restart first. If errors persist, roll back to the previous image (see §5).

### 7.3 LoginFailureSpike

**Means:** > 1 bad-credentials/sec sustained for 10 minutes. Probably credential stuffing, possibly a broken client.

1. Check source IP distribution: `docker compose logs --since 30m nginx | grep " 401 " | awk '{print $1}' | sort | uniq -c | sort -rn | head`
2. If single IP: ban it at nginx (`deny` directive in `nginx.prod.conf`, then `docker compose restart nginx`).
3. If many IPs: it's likely distributed stuffing. Contact-link: notify stakeholders; consider temporarily tightening the login throttle (currently `5/minute` per IP in `DEFAULT_THROTTLE_RATES`).

### 7.4 BillingWebhookFailures

**Means:** > 5% of Razorpay webhooks failing for 10 minutes. **Critical** — subscription state drifting from Razorpay's.

1. `docker compose logs --tail 200 backend | grep -iE "webhook|razorpay"` — what's the error?
2. Common causes:
   - HMAC signature mismatch → `RAZORPAY_WEBHOOK_SECRET` changed in Razorpay dashboard but not in `.env`
   - Plan ID mapping broken → new plan in Razorpay dashboard not added to `SubscriptionPlan` table
   - DB write fails → check `db` container health
3. Razorpay retries individual webhooks for up to 24 hours — fix the root cause and they'll eventually catch up. Do NOT manually replay events without checking `PaymentEvent` idempotency first.

### 7.5 PlanLimitFailOpen

**Means:** `PlanLimitMiddleware` fell open more than 3 times in 5 minutes. Paying customers are currently **not** being quota-enforced.

1. Immediate: check Redis (`docker compose exec redis redis-cli -a "$REDIS_PASSWORD" PING`) and Postgres (`docker compose exec db pg_isready -U postgres`).
2. `docker compose logs --tail 200 backend | grep -i "PlanLimitMiddleware"` — cache or DB error?
3. If Redis is down: `docker compose restart redis`. Expect ~30s of cold cache afterward.
4. If DB is down: this is a bigger incident — follow the db-down playbook (not written yet — TODO).

**Revenue risk:** while this alert is firing, any tenant that is over-quota is getting free screenings. Check `select count(*), organization_id from screening_screening where created_at > <start_of_incident> group by organization_id order by 1 desc limit 10` after recovery to see if you need to bill anyone retroactively.

### 7.6 BackupMissing

**Means:** no successful DB backup has been recorded in Prometheus for 25+ hours. **Critical** — patient data is single-copy.

1. Check `BACKUP_S3_BUCKET` is set: `docker compose exec backend env | grep BACKUP_S3_BUCKET`
2. Check the beat schedule: `docker compose logs --since 26h celery_beat | grep backup`
3. Check the task ran: `docker compose logs --since 26h celery_worker | grep -E "backup_complete|backup_pg_dump_failed|backup_upload_failed"`
4. Common causes:
   - `BACKUP_S3_BUCKET` unset in `.env`
   - AWS credentials rotated but not updated in `.env`
   - S3 bucket deleted or permissions changed
   - Celery beat stopped scheduling (check `celery_beat` container health)
5. Manually trigger a backup: `docker compose exec celery_worker celery -A clinomic call core.backup_database`

**Do not dismiss this alert.** If you can't fix it in 30 minutes, take a manual `pg_dump` to a local file on the VM and copy it off-box.

---

## 8. Secrets and `.env`

The `.env` file at `/opt/clinomic-b12-platform/.env` holds everything:

- `POSTGRES_PASSWORD`, `REDIS_PASSWORD`
- `DJANGO_SECRET_KEY`, `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`
- `MASTER_ENCRYPTION_KEY` (Fernet — rotating this breaks ALL encrypted PHI)
- `AUDIT_SIGNING_KEY`
- `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`
- `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`
- `SENTRY_DSN`, `GRAFANA_ADMIN_PASSWORD`, `DISCORD_ALERT_WEBHOOK_URL`
- `BACKUP_S3_BUCKET`, `AWS_BACKUP_ACCESS_KEY_ID`, `AWS_BACKUP_SECRET_ACCESS_KEY`

**Rotation procedure** (no-downtime for most keys):

1. Edit `/opt/clinomic-b12-platform/.env` on the VM (owned by `deploy:deploy`, `chmod 600`)
2. `docker compose -f docker-compose.prod.yml up -d --force-recreate <affected-services>`
3. Verify `/api/health/live` still 200s

**Do NOT rotate `MASTER_ENCRYPTION_KEY` without a data migration** — all encrypted PHI will be unreadable. If you must, the migration plan needs dual-key support; ask before touching it.

---

## 9. Known gaps / accepted risks (as of 2026-04-15)

- **No external uptime ping.** Monitoring runs on the same VM it monitors. A full-VM outage is invisible to alerting. **Fix:** UptimeRobot / UptimeKuma pointing at `https://clinomiclabs.com/api/health/live` from outside the box. 10-minute setup. Single highest-ROI action if not already done.
- **Single VPS, no HA.** Hardware failure → down until BigRock reboots or we rebuild. Accept for now; migrate to HA when user count justifies.
- **`docker compose down -v` will wipe Postgres.** The `postgres_data` named volume has no bind-mount backup. **Do NOT pass `-v` on the prod host.**
- **Redis has no AOF** (`--save 60 1` only). On crash we lose up to 60s of broker messages and cache state. Tasks in flight are protected by `acks_late`; queued-but-not-delivered messages are not.
- **Sync tenant provisioning.** SUPER_ADMIN `POST /platform/orgs/create/` runs schema creation synchronously inside a request (5-15s). If you click create twice fast, the second request may timeout. Onboard labs one at a time.
- **Login throttle 5/min per IP.** Demos with > 5 users on one wifi trip the throttle; space logins 15s apart or tether to mobile hotspot.

---

## 10. When to escalate

- Data loss suspected → page Param immediately, do NOT attempt recovery alone
- Prolonged outage (> 30 min) → communicate on Discord #incidents, consider status page
- Security incident (credential stuffing, confirmed breach, suspicious admin actions) → preserve logs, rotate all secrets, escalate to legal/compliance
- Any HIPAA-adjacent PHI exposure → escalate immediately, log everything you did in `docs/INCIDENTS/YYYY-MM-DD.md`

---

## 11. Deploy cheat sheet

Normal deploy: push to `master`, CI runs, auto-deploys.

```bash
# Manual deploy from a known-good SHA (emergency only)
cd /opt/clinomic-b12-platform
BACKEND_TAG=<sha> FRONTEND_TAG=<sha> \
  docker compose -f docker-compose.prod.yml pull
BACKEND_TAG=<sha> FRONTEND_TAG=<sha> \
  docker compose -f docker-compose.prod.yml up -d --force-recreate
```

Stop everything (maintenance window):

```bash
docker compose -f docker-compose.prod.yml stop
# ... work ...
docker compose -f docker-compose.prod.yml start
```

**Never** `docker compose down -v` (wipes volumes).
**Never** `docker system prune -a --volumes` (same).

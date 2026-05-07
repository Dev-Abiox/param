# Production Seamlessness Audit

**Date:** 2026-04-17
**Target:** `param` — Clinomic B12 Screening SaaS, single BigRock VPS (`66.116.225.67`)
**Scope:** day-2 operational seamlessness — deploy path, failure recovery, scaling, observability, backup/DR, runbook, tenant isolation, config drift
**Out of scope:** launch blockers, security, UX (covered in prior audits)

---

## Executive summary

The platform can run in production for a single operator with moderate traffic: the deploy pipeline auto-rolls-back on migration or healthcheck failure, monitoring covers the five highest-value application metrics, daily local backups are running, and the runbook has playbooks for every alert rule. However, there are real seams that will cut operators on a bad day: the prod nginx mount silently uses `nginx.testing.conf` (the "prod" file is dead), uptime monitoring lives inside the box it's meant to monitor so a full-VM outage is invisible, **offsite backups are not configured so RPO is effectively one VM-loss = total data loss**, and the deploy window has a ~45-60s cold period during `--force-recreate` where nginx cannot reach backend. The "can the team actually run this" answer is **yes for low traffic, no for any incident that requires the VM itself to have failed**.

---

## Scope + methodology

Code reviewed in the repository at `C:\Users\Admin\param`. All findings cite file:line. SSH into prod VM (`66.116.225.67`) was attempted for live verification but was blocked by the local sandbox — findings that would require shelling in are marked "not verified on live VM" below.

Eight operational domains audited:

1. Deploy path (CI → prod) — [.github/workflows/production-deploy.yml](../../.github/workflows/production-deploy.yml), [docker-compose.prod.yml](../../docker-compose.prod.yml)
2. Failure recovery — Redis/Postgres/Celery/nginx/disk
3. Scaling cliffs — PgBouncer, uvicorn, CatBoost, Celery queues
4. Observability — [monitoring/prometheus/alerts.yml](../../monitoring/prometheus/alerts.yml), [monitoring/alertmanager/alertmanager.tmpl.yml](../../monitoring/alertmanager/alertmanager.tmpl.yml), Grafana, Uptime-Kuma
5. Backup + DR — [scripts/db-backup.sh](../../scripts/db-backup.sh), [backend_v3/apps/core/tasks.py](../../backend_v3/apps/core/tasks.py), [scripts/restore_test.sh](../../scripts/restore_test.sh)
6. Runbook — [docs/RUNBOOK.md](../RUNBOOK.md)
7. Tenant isolation — [backend_v3/apps/billing/middleware.py](../../backend_v3/apps/billing/middleware.py)
8. Config drift — `.env` on VM, compose copy flow

---

## Findings

### Deploy path

**D1 (important). Nginx in production serves the *testing* config file; the "prod" file is dead code.** [docker-compose.prod.yml:185](../../docker-compose.prod.yml#L185) mounts `./nginx.testing.conf:/etc/nginx/nginx.conf:ro`. [nginx.prod.conf](../../nginx.prod.conf) is never loaded. The testing conf does handle both `clinomiclabs.com` and `testing.clinomiclabs.com` server blocks ([nginx.testing.conf:74-174](../../nginx.testing.conf)) so prod traffic works — but any future edit to `nginx.prod.conf` (a reasonable name to edit) will silently have zero effect. The two files have diverged: `nginx.prod.conf` has `admin_limit` rate zone and richer CSP/security headers; `nginx.testing.conf` blocks `/metrics` outright (`deny all; return 404`) where prod allows it from internal nets.

**D2 (important). Deploy has a ~45-60s hard cut where requests to backend fail.** [.github/workflows/production-deploy.yml:279](../../.github/workflows/production-deploy.yml#L279) runs `docker-compose up -d --force-recreate` which stops all backend/frontend/celery/nginx containers before starting the new ones, then [.github/workflows/production-deploy.yml:282](../../.github/workflows/production-deploy.yml#L282) sleeps 30s and only *then* runs migrations and healthchecks. Active user requests during this window get TCP-reset or 502. No blue/green, no draining. For a 1-VPS topology this is probably acceptable, but it is not documented as a user-visible deploy window anywhere.

**D3 (important). `migrate_schemas` runs twice per deploy — once during deploy workflow (with rollback), once at container startup (without).** The workflow does `migrate_schemas --shared` then `migrate_schemas` with explicit rollback on failure ([.github/workflows/production-deploy.yml:289-307](../../.github/workflows/production-deploy.yml#L289-L307)). But the backend container command *also* runs `python manage.py migrate_schemas --noinput` at startup ([docker-compose.prod.yml:113](../../docker-compose.prod.yml#L113)). If a tenant schema migration fails partway through (e.g. 3 of 5 tenants applied, 4th fails), the workflow catches it and rolls back the *image*, but the partially-migrated tenants remain migrated on the old image — which may be incompatible with the old code. Recovery requires either manual `migrate <app> <prev_migration>` (and hoping it's reversible) or DB restore. This is the single biggest unseen deploy risk.

**D4 (nice-to-have). Rollback re-pins tags via the PREV_* variables but only looks at the *backend* container's current tag** ([.github/workflows/production-deploy.yml:262-267](../../.github/workflows/production-deploy.yml#L262-L267)). If `celery_worker`, `celery_email_worker`, `celery_beat` are pinned to the same tag, rollback updating only `BACKEND_TAG`/`FRONTEND_TAG` will leave them on the bad SHA until they naturally restart (`restart: always` won't re-pull a new tag). Verification: [docker-compose.prod.yml:231](../../docker-compose.prod.yml#L231), [docker-compose.prod.yml:298](../../docker-compose.prod.yml#L298), [docker-compose.prod.yml:349](../../docker-compose.prod.yml#L349) all use `${BACKEND_TAG:-latest}` — so `--force-recreate` with the exported var will in fact re-pin them. OK under the current command (`up -d --force-recreate` recreates everything), but fragile.

**D5 (nice-to-have). The `:latest` tag is retagged locally after pull** ([.github/workflows/production-deploy.yml:274-275](../../.github/workflows/production-deploy.yml#L274-L275)) so the `PREV_BACKEND_TAG` lookup via `docker inspect` will always return `latest` on the *second* and subsequent deploys (because the previously-running container was started from the freshly-retagged `:latest`, not the SHA). The intent — pin prev exactly — is partially defeated. In practice it still rolls back to the prior image because Docker's image ID for `:latest` still points at the prior digest until the new pull happens, but the tag string captured in `PREV_BACKEND_TAG` is `latest`, not a SHA. Logs will say "Rolling back to latest" which is confusing during incident response.

### Failure recovery

**F1 (critical). Redis is a single point of failure for *everything*: cache, Celery broker, Channels, PlanLimitMiddleware, rate limiting.** [docker-compose.prod.yml:93-96](../../docker-compose.prod.yml#L93-L96), [backend_v3/clinomic/settings.py:309-325](../../backend_v3/clinomic/settings.py#L309-L325). If Redis dies for 30s:
- WebSocket connections hang/disconnect (Channels layer backed by Redis DB 2)
- Celery task dispatch fails; new webhooks, emails, usage increments pile up in memory and eventually 500
- `PlanLimitMiddleware` *fail-opens* (correct behavior per [backend_v3/apps/billing/middleware.py:265-312](../../backend_v3/apps/billing/middleware.py#L265-L312)) — paying customers get free screenings for the duration
- `OrgRateLimitMiddleware` also fail-opens ([backend_v3/apps/billing/middleware.py:211-213](../../backend_v3/apps/billing/middleware.py#L211-L213))
- Sessions do **not** break: Django's default `SESSION_ENGINE` is DB-backed and no override is set (verified — no `SESSION_ENGINE` in settings). This is good.

Redis has `--save 60 1` only ([docker-compose.prod.yml:209](../../docker-compose.prod.yml#L209)), no AOF — on crash we lose up to 60s of broker queue state. Tasks in-flight are protected by `acks_late` ([backend_v3/clinomic/settings.py:339-340](../../backend_v3/clinomic/settings.py#L339-L340)) but queued-but-not-yet-delivered messages are lost. This is documented in [docs/RUNBOOK.md:356](../RUNBOOK.md#L356) but not mitigated.

**F2 (important). Postgres death returns Django 500s, not a maintenance page.** No circuit breaker, no cached "try again in a moment" response. Health endpoint [backend_v3/apps/core/views.py:664-674](../../backend_v3/apps/core/views.py#L664-L674) does `connection.ensure_connection()` and returns 500 on DB unavailable. Nginx has no fallback — user sees backend 500/502.

**F3 (important). Celery worker healthcheck is `inspect ping` with 10s timeout** ([docker-compose.prod.yml:239](../../docker-compose.prod.yml#L239)). `inspect ping` talks through the broker (Redis). If Redis is slow but not dead, the healthcheck fails and Docker restarts the worker — which does not fix the actual problem and takes healthy workers down. Worse: when Redis comes back, *both* workers may be in a restart loop while Celery's discovery rebinds.

**F4 (nice-to-have). Nginx restart: uvicorn workers receive SIGTERM when the nginx container depends_on `backend: service_healthy` fails, but nginx itself doesn't restart cleanly.** TLS certs are bind-mounts from the host Letsencrypt dir ([docker-compose.prod.yml:186-189](../../docker-compose.prod.yml#L186-L189)) — `certbot renew` hook must reload nginx. No evidence of a certbot deploy-hook in the repo. If certs rotate and nginx isn't reloaded, HTTPS breaks 60 days from first issue date.

**F5 (nice-to-have). Disk fill behavior is not bounded.** No log rotation config in docker-compose (no `logging: driver: json-file, options: max-size`). Default docker json-file driver will grow unbounded. [.github/workflows/production-deploy.yml:246-249](../../.github/workflows/production-deploy.yml#L246-L249) prunes images/volumes on *each deploy* — so disk is only cleaned on deploy cadence. Between deploys (1-2 weeks), a chatty backend log can fill `/var/lib/docker`. Prometheus itself has `--storage.tsdb.retention.time=30d` ([docker-compose.prod.yml:400](../../docker-compose.prod.yml#L400)) which is bounded, good.

### Scaling cliffs

**S1 (important). Uvicorn 4 workers × PgBouncer pool 40 is balanced for current topology, but the math is tight.** [docker-compose.prod.yml:116](../../docker-compose.prod.yml#L116): `--workers 4`. [docker-compose.prod.yml:39](../../docker-compose.prod.yml#L39): `DEFAULT_POOL_SIZE: 40`. With 4 uvicorn + celery_worker (concurrency=2) + celery_email_worker (concurrency=4) + celery_beat = ~11 Django processes. At peak each can hold 2-3 transactions open (Django's per-request conn + any background). Pool 40 gives ~3.6 per process — enough for steady state but a single slow query will pile up clients and hit `RESERVE_POOL_TIMEOUT=3s` ([docker-compose.prod.yml:43](../../docker-compose.prod.yml#L43)) causing `cl_waiting` spikes. Not currently alerted on — see O2.

**S2 (important). CatBoost model memory is per-uvicorn-worker AND per-celery-worker.** Every worker process in `ghcr.io/dev-abiox/param` imports Django + CatBoost at boot (~60MB baseline per the compose comment at [docker-compose.prod.yml:293-297](../../docker-compose.prod.yml#L293-L297)). The ML engine loads the full model on first predict in each process — so N uvicorn + 2 celery default + 4 celery email + 1 celery beat = 11 processes can each hold a model copy. Backend container cap is 2GB ([docker-compose.prod.yml:143-148](../../docker-compose.prod.yml#L143-L148)). If CatBoost is 200MB resident × 4 uvicorn = 800MB just in the backend container; predictions are bounded by `ML_EXECUTOR_WORKERS=4` ([backend_v3/clinomic/settings.py:288](../../backend_v3/clinomic/settings.py#L288)) threads within the process. OOM risk rises if concurrency × batch size grows.

**S3 (important). Celery email worker concurrency=4 is a rate-limit issue with SMTP provider.** [docker-compose.prod.yml:303](../../docker-compose.prod.yml#L303): `--concurrency=4 -Q email`. `mail.arogyabiox.com` provider rate limit unknown (not documented). A signup burst will fan out welcome + credentials + MFA OTP emails across 4 workers concurrently; if the provider rate-limits at 2/s, tasks will retry and pile up on `email` queue with no backpressure surfacing to users (the request that triggered the email already returned 200).

**S4 (nice-to-have). No alert on Postgres connection exhaustion.** With `MAX_CLIENT_CONN=200` ([docker-compose.prod.yml:40](../../docker-compose.prod.yml#L40)) in PgBouncer and Postgres default `max_connections=100`, the saturation point is knowable but not monitored. The runbook manual check at [docs/RUNBOOK.md:105-114](../RUNBOOK.md#L105-L114) is reactive, not proactive.

### Observability

**O1 (critical). Uptime monitoring runs *on the same VM it monitors*.** [docker-compose.prod.yml:465-481](../../docker-compose.prod.yml#L465-L481) runs Uptime-Kuma in the same compose stack on port 3001. If the VM dies or loses network, neither Prometheus nor Uptime-Kuma nor Alertmanager can alert — Discord will hear nothing. [docs/RUNBOOK.md:78](../RUNBOOK.md#L78) and [docs/RUNBOOK.md:353](../RUNBOOK.md#L353) *correctly* identify this as the single highest-ROI gap but the gap has not been closed — Uptime-Kuma was added but remains co-located. Fix needs an off-box ping: UptimeRobot free tier or second VPS pinging `/api/health/live`.

**O2 (important). The 5 alert rules are thin for a production system.** [monitoring/prometheus/alerts.yml](../../monitoring/prometheus/alerts.yml) defines: HighPredictLatency, PredictErrorSpike, LoginFailureSpike, BillingWebhookFailures, PlanLimitFailOpen, BackupMissing. What is **not** alerted:
- Container down / restart loop (no `up{job="clinomic-backend"} == 0` rule)
- Postgres down (Prometheus has no pg_exporter scraped)
- Redis down (same)
- Disk > 80% or 90%
- Memory > 85% (OOMkills silent)
- Celery queue depth growing (email queue stall)
- Nginx 5xx rate
- TLS cert expiry
- Razorpay API 4xx (client bug → webhook never fires, BillingWebhookFailures can't catch that)

A backend OOM that flaps every 10 minutes would trigger `PredictErrorSpike` only *if* screening traffic is high enough — otherwise silent. [monitoring/prometheus.yml:13-18](../../monitoring/prometheus.yml#L13-L18) only scrapes `backend:8000/metrics` — no node-exporter, no cAdvisor, no pg-exporter.

**O3 (important). Alertmanager sends to one Discord webhook — there's no escalation, no PagerDuty, no phone.** [monitoring/alertmanager/alertmanager.tmpl.yml:22-50](../../monitoring/alertmanager/alertmanager.tmpl.yml#L22-L50). If the on-call is asleep with Discord muted, a critical (`BackupMissing`, `PredictErrorSpike`, `BillingWebhookFailures`) waits until morning. `repeat_interval: 1h` for critical means 24 repeats overnight, but Discord DND swallows them.

**O4 (nice-to-have). Logs are structlog JSON** ([backend_v3/clinomic/settings.py:448-470](../../backend_v3/clinomic/settings.py#L448-L470)) — good for grep, but there's no central log store. If the backend container is recycled (e.g. OOM + auto-restart), docker logs for the killed container are retained but the RUNBOOK's `docker compose logs` commands only show the *current* container. Post-mortem on a flapping container is hard.

**O5 (nice-to-have). No traces (OTEL/Tempo/Jaeger).** A slow `/api/screening/predict` shows up in Prometheus as p95 > 1s but there's no way to see whether the time was in DB, ML, or Python. Debugging needs live reproduction.

### Backup + DR

**B1 (critical). Offsite backup is not configured. RPO = "none" if the VM is lost.** [scripts/db-backup.sh:42](../../scripts/db-backup.sh#L42) dumps to `/opt/backups/clinomic/` on the same disk as the database. [backend_v3/apps/core/tasks.py:143-146](../../backend_v3/apps/core/tasks.py#L143-L146) returns `skipped` when `BACKUP_S3_BUCKET` is empty, which per the auto-memory (userEmail context) is the current state. The `BackupMissing` alert *does* fire when the Prometheus gauge is `absent()` ([monitoring/prometheus/alerts.yml:121-123](../../monitoring/prometheus/alerts.yml#L121-L123)) so at least the gap is visible. But practically: **VM loss today = total data loss back to the most recent manual laptop pull.** The "manual pull" section in [docs/RUNBOOK.md:220-252](../RUNBOOK.md#L220-L252) is a coping mechanism, not a backup system — it depends on a human remembering to run `scp`.

**B2 (critical). RTO for full VM loss is untested and likely >8 hours.** No runbook for "the VM dies, stand up a new one". Components that would need reconstruction:
- Provision new BigRock VPS (or other provider)
- Run `scripts/vm-setup/01-04*.sh` (these exist, good)
- Restore `.env` (not backed up anywhere — this is separate from the DB backup)
- Restore `/etc/letsencrypt/live/*` (TLS certs — not in backup)
- Restore DB from most-recent-available `pg_dump`
- Point DNS
- Validate Razorpay webhook target in their dashboard

None of this is in the runbook. The restore drill at [scripts/restore_test.sh](../../scripts/restore_test.sh) only validates DB-to-scratch-db on the same VM — it does not validate cross-VM recovery.

**B3 (important). Two different backup mechanisms exist, out of sync.** [scripts/db-backup.sh](../../scripts/db-backup.sh) (host cron, plain SQL + gzip, 7-day retention on local disk) vs. [backend_v3/apps/core/tasks.py:131-222](../../backend_v3/apps/core/tasks.py#L131-L222) (Celery task, pg_dump custom format + gzip, uploads to S3). They run at different times (02:00 host cron vs 03:00 beat), use different formats, and the Prometheus gauge only tracks the S3 one. If an operator sees `/opt/backups/clinomic/` populated they may incorrectly think offsite is working. [scripts/restore_test.sh:116-117](../../scripts/restore_test.sh#L116-L117) defaults to local-file mode — drill passes even when S3 upload hasn't been running for a week.

**B4 (nice-to-have). `.env` has no backup.** The VM `.env` at `/opt/clinomic-b12-platform/.env` contains `MASTER_ENCRYPTION_KEY`, `AUDIT_SIGNING_KEY`, JWT secrets, Razorpay creds — none of which are recoverable from GitHub. If the file is corrupted or the VM disk dies before recovery, **all encrypted PHI becomes unreadable forever** (per [docs/RUNBOOK.md:346](../RUNBOOK.md#L346): "rotating MASTER_ENCRYPTION_KEY breaks ALL encrypted PHI").

### Runbook quality

**R1 (nice-to-have). Runbook is unusually good for this stage of a project** — [docs/RUNBOOK.md](../RUNBOOK.md) has per-alert playbooks (§7.1-7.6), first-60-seconds triage (§2), rollback procedure (§5), and a known-gaps section (§9) that honestly lists limitations. I traced the `BillingWebhookFailures` playbook ([docs/RUNBOOK.md:288-297](../RUNBOOK.md#L288-L297)) end-to-end: it correctly identifies the three likely causes (HMAC secret mismatch, plan ID mapping, DB write fail), gives the exact `grep` command, and warns about Razorpay retry semantics before manual replay. A tired on-call could follow it.

**R2 (important). The `db-down` playbook is admitted as TODO.** [docs/RUNBOOK.md:306](../RUNBOOK.md#L306): "this is a bigger incident — follow the db-down playbook (not written yet — TODO)". For a patient-data platform, DB down is the most critical scenario and has no written response.

**R3 (nice-to-have). Runbook assumes `clinomic` SSH alias is configured on the dev laptop** [docs/RUNBOOK.md:222](../RUNBOOK.md#L222). If the laptop is lost or someone else has to respond, the manual-pull backup path fails. The alias config is not documented in the repo.

### Tenant isolation

**T1 (important). JWTTenantMiddleware sets `connection.set_tenant()` per request, but `connection` is process-global.** [backend_v3/apps/billing/middleware.py:99](../../backend_v3/apps/billing/middleware.py#L99). Under Django ASGI + uvicorn, each worker process has one DB connection that's reused across async requests. If two concurrent async requests hit the same worker for different tenants, the `set_tenant` call on request B can overwrite the search_path while request A is mid-query. This is a known django-tenants caveat — the fix is per-request connection, which neither django-tenants nor this middleware implements.

Verified by reading: no explicit `async_to_sync` or per-request connection pooling. Not verified on live VM. Under current low concurrency the race window is small; under load the blast radius is "DOCTOR on tenant A sees tenant B data intermittently" — a cross-tenant breach.

**T2 (nice-to-have). SUPER_ADMIN auto-tenant resolution picks "first non-public tenant".** [backend_v3/apps/billing/middleware.py:151-158](../../backend_v3/apps/billing/middleware.py#L151-L158). Non-deterministic — any super-admin action without `X-Org-Id` acts on whatever tenant happens to sort first by `created_at`. Not a seamlessness bug per se, but surprising and could cause wrong-tenant writes during incident response.

### Config drift

**C1 (important). `.env` on the VM is the source of truth for all secrets and has zero validation.** A typo like `REDIS_PASSWORD=abc def` (unquoted space) or `POSTGRES_PASSWORD="quoted"` (double-quote that shell source-includes but Python gets wrong) will cause subtle failures. Deploy workflow uses `set -a; source "$BASE/.env"; set +a` ([.github/workflows/production-deploy.yml:233-236](../../.github/workflows/production-deploy.yml#L233-L236)) — if the file has a syntax error, bash will error during deploy and half the containers may be in an inconsistent state. There is a `validate_required_secrets()` call at [backend_v3/clinomic/settings.py:403-412](../../backend_v3/clinomic/settings.py#L403-L412) that checks *presence* but not *validity* of each secret.

**C2 (important). `docker-compose.prod.yml` is overwritten on each deploy** ([.github/workflows/production-deploy.yml:189](../../.github/workflows/production-deploy.yml#L189)). Any on-VM edit (e.g. quick `DEFAULT_POOL_SIZE` bump during an incident per runbook §4.3) is silently discarded on next push to master. Not documented in runbook §9 or §11. Operators will edit thinking "this is the live file" — it is, until the next CI run.

---

## Prioritized gap list

| # | Gap | Impact | Effort to close |
|---|-----|--------|-----------------|
| 1 | **No offsite backup** (B1) | Data loss on VM failure | **1 hour** — configure Cloudflare R2 (free tier), set 4 env vars per [docs/BACKUP_SETUP.md](../BACKUP_SETUP.md); offsite within 24h |
| 2 | **No external uptime ping** (O1) | Full-VM outage is silent | **15 min** — UptimeRobot free tier → /api/health/live |
| 3 | **No VM-loss recovery runbook** (B2) | RTO 8h+ untested | **3 hours** — write it, do a paper drill |
| 4 | **`.env` has no backup or validation** (B4, C1) | Secret loss = PHI loss forever | **30 min** — encrypted copy in ops vault, shell pre-validation |
| 5 | **Dead nginx.prod.conf / wrong file mounted** (D1) | Config edits silently no-op | **10 min** — delete nginx.prod.conf OR fix the mount |
| 6 | **No container-down / DB-down / disk / memory alerts** (O2) | Major outages silent until user complains | **2 hours** — add 6-8 Prometheus rules, scrape node-exporter + postgres-exporter |
| 7 | **No db-down playbook** (R2) | Biggest incident has no written response | **1 hour** — write it |
| 8 | **Double `migrate_schemas` — partial tenant migration on failure** (D3) | Deploy rollback restores image but not DB | **2 hours** — remove startup `migrate_schemas`, rely on CI-side only |
| 9 | **Deploy downtime 45-60s** (D2) | User-visible 502s on every push | **4-8 hours** — run two backend replicas behind nginx with rolling recreate |
| 10 | **No alert escalation off Discord** (O3) | Critical alert swallowed by muted channel | **1 hour** — add email receiver, or PagerDuty free tier |
| 11 | **PgBouncer pool saturation not alerted** (S4) | First sign of DB contention invisible until queries timeout | **1 hour** — postgres-exporter + one alert rule |
| 12 | **Async tenant race in JWTTenantMiddleware** (T1) | Potential cross-tenant data leak under load | **Medium — needs per-request connection or sync-only view mode** |
| 13 | **On-VM compose edits silently overwritten** (C2) | Incident patches lost on next push | **10 min** — one sentence in RUNBOOK §9 |
| 14 | **Celery worker healthcheck tied to Redis** (F3) | Redis hiccup → worker restart storm | **30 min** — use local Python check instead of inspect ping |
| 15 | **Docker log rotation unbounded** (F5) | Disk fills between deploys | **15 min** — add `logging:` block to compose |
| 16 | **Backup dual-source confusion** (B3) | Green local backup masks missing offsite | **15 min** — deprecate `db-backup.sh` in favor of Celery task |
| 17 | **Rollback tag captured as `:latest` not SHA** (D5) | Rollback logs confusing in incident | **30 min** — inspect image digest, not tag |
| 18 | **No certbot deploy-hook to reload nginx** (F4) | Cert rotation breaks HTTPS at 60 days | **15 min** — add `--deploy-hook 'docker exec nginx nginx -s reload'` |

## What works well

- **Deploy auto-rollback on migration and healthcheck failure** ([.github/workflows/production-deploy.yml:289-319](../../.github/workflows/production-deploy.yml#L289-L319)) — a bad image really does get backed out without human intervention. This is better than most startups have.
- **Runbook has real playbooks for every active alert rule** ([docs/RUNBOOK.md §7](../RUNBOOK.md#L256)). The BillingWebhookFailures playbook is correct end-to-end.
- **PlanLimitMiddleware fail-open is instrumented with a metric** ([backend_v3/apps/billing/middleware.py:326-337](../../backend_v3/apps/billing/middleware.py#L326-L337)) *and* alerted on ([monitoring/prometheus/alerts.yml:90-109](../../monitoring/prometheus/alerts.yml#L90-L109)) — the revenue-at-risk state is visible, debounced, and actionable.
- **Sessions are DB-backed by default** — Redis outage doesn't log users out.
- **Celery has `acks_late + reject_on_lost`** ([backend_v3/clinomic/settings.py:339-340](../../backend_v3/clinomic/settings.py#L339-L340)) — a worker crash doesn't drop in-flight tasks.
- **Restore drill script is real and tenant-aware** ([scripts/restore_test.sh:180-219](../../scripts/restore_test.sh#L180-L219)) — it counts per-tenant screenings, not just "the dump loaded".
- **Resource limits on every service** ([docker-compose.prod.yml:20-28](../../docker-compose.prod.yml#L20-L28) etc.) — one runaway container can't starve the VM.
- **Image tags pinned by SHA at deploy time** ([.github/workflows/production-deploy.yml:217-223](../../.github/workflows/production-deploy.yml#L217-L223)) — deploys are reproducible even as `:latest` moves.

---

## Tested vs untested

**Verified by reading code** (source-of-truth found in repo):
- Deploy workflow flow, rollback conditions, migration behavior
- Compose service definitions, resource limits, healthcheck commands
- Middleware fail-open paths and metric instrumentation
- Alert rule expressions and alertmanager routing
- Runbook coverage of each alert rule
- Backup task logic and S3-skip behavior
- Nginx config *as loaded* (vs. the dead `nginx.prod.conf`)
- Celery beat schedule and queue routing
- Django settings for session / cache / channels backends

**Would have been verified by live check on prod VM** (paramiko SSH was attempted but blocked by local sandbox):
- Actual running container SHAs vs. `:latest`
- Current `BACKUP_S3_BUCKET` value in `.env`
- `/opt/backups/clinomic/` retention state
- Crontab for `db-backup.sh`
- UFW rules and whether uptime-kuma port 3001 is externally reachable
- Free disk, memory, load
- Whether Uptime-Kuma has monitors configured (or is just running empty)

**Not verified (would require destructive testing):**
- Actual deploy downtime measured in seconds
- Redis-down failure cascade behavior
- Tenant race condition in middleware under concurrent async load
- Full VM-rebuild RTO
- Celery email worker behavior at SMTP rate limit
- PgBouncer saturation point under real tenant growth

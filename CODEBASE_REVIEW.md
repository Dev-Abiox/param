# Codebase Review — Clinomic B12 Screening Platform

**Date:** 2026-02-20
**Branch:** `claude/review-codebase-RcqD6`

---

## 1. Project Overview

**Clinomic** is a multi-tenant healthcare SaaS platform for **B12 deficiency screening** using CBC (Complete Blood Count) analysis. It employs a two-stage CatBoost ML model with rule-based clinical adjustments to classify patients as Normal, Borderline, or Deficient.

### Tech Stack

| Layer          | Technology                                                             |
| -------------- | ---------------------------------------------------------------------- |
| Backend        | Django 4.x + DRF, `django-tenants` for multi-tenancy                  |
| Frontend       | React 18, Tailwind CSS, shadcn/ui (Radix), Recharts, React Router v6  |
| Database       | PostgreSQL 15 (schema-per-tenant via `django-tenants`)                 |
| ML Engine      | CatBoost (via joblib), two-stage pipeline                              |
| Task Queue     | Celery + Redis (worker + beat scheduler)                               |
| Caching        | Redis                                                                  |
| Auth           | Custom JWT (access + refresh with httpOnly cookie rotation)            |
| MFA            | TOTP via `pyotp` with backup codes                                     |
| Encryption     | Fernet (AES-128-CBC) field-level PHI encryption                        |
| Deployment     | Docker Compose, nginx reverse proxy, GHCR images, GitHub Actions CI/CD |
| Monitoring     | Sentry (optional), structlog (JSON in prod)                            |

### Key Business Modules

- **Screening** — CBC-based B12 risk prediction with consent workflow
- **Work Queue** — LAB triage queue with status transitions (pending → in_progress → completed)
- **Doctor Review** — Clinical note and approval workflow
- **Analytics** — Dashboard stats, lab/doctor drill-down, patient CBC trend
- **Bulk Import** — Async CSV import via Celery
- **FHIR R4** — Accepts FHIR Bundles with LOINC-coded Observations
- **Audit** — HMAC-signed, hash-chained immutable audit log for HIPAA compliance

---

## 2. Architecture Assessment

### Strengths

1. **Multi-tenancy done right** — `django-tenants` with schema-per-org gives strong data isolation at the DB level. Shared apps (auth, core) vs. tenant apps (screening, analytics) are cleanly separated.

2. **PHI protection** — Patient name, age, and sex are encrypted at rest using Fernet. Decryption is via `@property` accessors on the `Patient` model, keeping encryption transparent to business logic.

3. **Audit trail** — Hash-chained, HMAC-signed `AuditLogEntry` records with `select_for_update()` to ensure sequence consistency under concurrency. This is a solid approach for HIPAA compliance evidence.

4. **JWT security** — Refresh tokens stored as SHA256 hashes, httpOnly cookie transport, SameSite=Strict, token rotation on each refresh, and all-token revocation on reuse detection (anti-replay). This is above-average JWT implementation.

5. **ML reproducibility** — Each screening stores `request_hash`, `response_hash`, `screening_hash`, and `model_artifact_hash`, enabling full reproducibility audits.

6. **Role-based access control** — Three roles (ADMIN, LAB, DOCTOR) with `HasRole` dynamic permission class. DOCTOR isolation is enforced at the view level (email-matched doctor records).

7. **Rate limiting** — Layered: nginx `limit_req_zone`, DRF throttle classes per endpoint (login: 5/min, MFA: 5/5min, screening: 50/min).

8. **Deployment pipeline** — CI runs backend pytest + frontend tests, builds Docker images, pushes to GHCR, deploys via SSH with health-check rollback.

### Areas of Concern

1. **No README** — The repository has no README.md. New developers have zero onboarding documentation.

2. **Settings duplication** — The `APP_ENV == 'production'` / `APP_ENV == 'prod'` blocks in `settings.py:240-260` are fully duplicated. This should be a single `if APP_ENV in ('production', 'prod'):` block.

3. **Celery broker/cache Redis DB mismatch** — `CACHES` uses `redis://redis:6379/1` while `CELERY_BROKER_URL` uses `redis://redis:6379/0`, but in `docker-compose.prod.yml` the celery_worker env sets `REDIS_URL=redis://redis:6379/0` while backend sets `REDIS_URL=redis://redis:6379/1`. The cache and broker use different Redis DBs, which is fine architecturally, but the env variable is reused with different values between services — this is fragile and could lead to cache/broker crossover if someone unifies them.

---

## 3. Backend Review

### Models (`apps/core/models.py`, `apps/screening/models.py`)

**Good:**
- UUID primary keys everywhere — prevents ID enumeration
- Proper `db_table` names and index definitions
- `PROTECT` on patient/lab foreign keys prevents accidental cascade deletions
- `AuditLogEntry` is well-designed with sequence, hash chain, and HMAC signature

**Issues:**

- **`Patient.unique_together = ['patient_id']`** (`screening/models.py:104`) — This is semantically incorrect. `unique_together` is for multi-field uniqueness constraints. A single field should use `unique=True` on the field itself. While Django will still create a unique constraint, it's misleading.

- **`MFASettings.secret_key` stored as `CharField(max_length=32)`** (`core/models.py:137`) — The comment says "Encrypted TOTP secret", but once encrypted with Fernet the ciphertext is ~120+ characters. If this field is actually storing Fernet-encrypted data, `max_length=32` will silently truncate. This needs to be a `TextField` or the max_length needs to be increased significantly.

- **`Notification.type` as CharField** — Should use `TextChoices` for type safety, consistent with how `Role`, `RiskClass`, and `ScreeningStatus` are handled.

### Views

**Good:**
- Clean separation of concerns — auth views in core, screening views in screening, analytics views in analytics
- Consistent use of `log_phi_access()` for audit trail
- DOCTOR isolation enforced in `ReviewScreeningView`, `CaseStatsView`, `PatientTrendView`, `ScreeningDetailView`
- Proper consent validation with expiry auto-detection in `PredictView`

**Issues:**

- **`CaseListView` applies slicing before filtering** (`screening/views.py:256-261`) — The `[:500]` slice happens before `.filter(doctor__code=...)`, meaning filters are applied to an already-truncated queryset. The filters should be applied before the slice.

- **`ConsentRevokeView` missing authorization** (`screening/views.py:376-389`) — Any authenticated user with MFA can revoke any consent by ID. There's no check that the revoking user is associated with the patient's lab or is an admin. This is a data integrity risk.

- **`ForgotPasswordView` logs the reset token** (`core/views.py:496`) — `logger.info("Password reset token for %s: %s", user.username, token)` writes the plaintext reset token to application logs. In production with a log aggregator, this token could be exposed. The comment says "For now, log the token for debugging" — this should be gated on `DEBUG` or removed entirely.

- **`PredictView` leaks exception details** (`screening/views.py:114`) — `f'Prediction failed: {str(e)}'` returns internal error details to the client. This could expose ML engine internals.

### Authentication (`apps/core/authentication.py`)

**Good:**
- HS256 JWT with proper `token_type` validation
- Refresh token rotation with hash-based storage
- Reuse detection revokes all tokens for the user
- MFA pending tokens are short-lived (5 minutes)

**Issues:**

- **Single JWT signing key** — Both access and refresh tokens use the same `JWT_SECRET_KEY` with HS256. If this key is compromised, both token types are compromised. Consider using separate keys or asymmetric signing (RS256).

- **No `jti` blacklist for access tokens** — If an access token is compromised, there's no way to revoke it before expiry (60 min default). Since refresh tokens have revocation, consider reducing access token lifetime to 15 minutes.

### ML Engine (`apps/screening/ml_engine.py`)

**Good:**
- Two-stage prediction with clinical rule adjustments
- Fail-closed behavior when models aren't ready
- Artifact hashing for version tracking
- Thread pool executor for async predictions

**Issues:**

- **CBC field name mismatch** — The serializer maps API fields to `Hb`, `RBC`, `HCT`, `MCV`, etc. via the `source` parameter, but the `predict()` method expects `Hb`, `RBC`, etc. The FHIR endpoint uses `Hb_g_dL`, `RBC_million_uL` naming. The view code passes `cbc` directly from the serializer, but the serializer's `source` renames create a dict with keys like `Hb` not `Hb_g_dL`. This works because the serializer transforms the keys, but the naming inconsistency makes the data flow hard to trace.

- **Global mutable singleton** (`_engine`) — The ML engine singleton is process-global. Under Gunicorn with multiple workers, each worker gets its own copy (fine), but there's no thread safety on the `_engine` initialization. A race condition is possible if two requests hit an uninitialized worker simultaneously.

### Celery Tasks

**Good:**
- HIPAA-compliant retention policy (7-year default)
- Database backup to S3 with gzip compression
- Bulk import with per-row progress tracking

**Issues:**

- **`backup_database` temp file not cleaned on success path edge cases** — The `finally` block tries to unlink `tmp_path`, but if the `try` block raises before `tmp_path` is assigned, this will raise `UnboundLocalError`. Move `tmp_path = None` before the try block and check `if tmp_path:` in finally.

- **Bulk import saves every row individually** — `process_bulk_import` does one `Patient.objects.update_or_create` + one `Screening.objects.create` + one `job.save()` per CSV row. For large imports (thousands of rows), this is N*3 DB queries. Consider batching with `bulk_create` for screenings and reducing save frequency.

---

## 4. Frontend Review

### Architecture

**Good:**
- Clean role-based routing in `App.js`
- In-memory access token (never in localStorage/sessionStorage)
- httpOnly cookie for refresh token — XSS cannot steal the refresh token
- Session timeout with 1-minute warning
- Separate axios instance (`_refreshAPI`) for token refresh to prevent interceptor loops
- i18n support via `i18next` (English + Arabic)

**Issues:**

- **`api.js` cache-busting parameter** — Every request appends `?r=<timestamp-random>` via the request interceptor. This defeats HTTP caching entirely and adds unnecessary payload to every request. If the goal is preventing browser caching, use `Cache-Control: no-cache` headers instead.

- **No error boundary** — The React app has no `ErrorBoundary` component. An unhandled error in any component will crash the entire application with a white screen.

- **Large UI component library** — 40+ shadcn/ui components are installed. Many appear unused (carousel, calendar, collapsible, etc.). This inflates the bundle size. Run a tree-shaking audit.

- **`--legacy-peer-deps` in CI** — The frontend CI step uses `npm ci --legacy-peer-deps`, indicating dependency version conflicts. These should be resolved rather than masked.

---

## 5. Security Review

### Strengths

- **PHI encryption at rest** — Fernet field-level encryption for patient PII
- **HIPAA audit trail** — Hash-chained, HMAC-signed, immutable audit log
- **MFA** — TOTP with rate-limited verification (5 attempts / 5 minutes)
- **Security headers** — HSTS, X-Frame-Options: DENY, X-Content-Type-Options, XSS Protection
- **nginx hardening** — Hidden files blocked, sensitive extensions denied, rate limiting
- **Password policy** — 12-character minimum with similarity/common/numeric validators
- **Startup secret validation** — Fails fast if secrets are placeholder values in production
- **Sentry PII filtering** — `send_default_pii=False`
- **Token security** — Refresh tokens in httpOnly/Secure/SameSite=Strict cookies

### Vulnerabilities / Risks

1. **`MFASettings.secret_key` max_length** — As noted above, if Fernet ciphertext exceeds 32 chars (it will), the TOTP secret gets silently truncated, potentially breaking MFA verification entirely in production.

2. **Password reset token in logs** — `ForgotPasswordView` logs plaintext reset tokens at INFO level.

3. **`ConsentRevokeView` authorization gap** — No ownership check on consent revocation.

4. **`clinical_note` field not sanitized** — `ReviewScreeningView` accepts `clinical_note` from `request.data` without any sanitization or length validation. If this note is rendered in a frontend context, XSS is possible. Even if rendered safely, there's no length limit.

5. **`client_max_body_size 100M` in nginx** — Generous for an API that primarily handles CBC data. The bulk import endpoint already limits to 10MB. Consider reducing the nginx limit to match.

6. **OpenAPI docs accessible without auth** — The `/api/docs/` and `/api/redoc/` endpoints serve the full API schema. In production, these should either be disabled or require authentication.

---

## 6. Testing Review

### Coverage

The test suite includes 9 test files:

| File                    | Scope                                          |
| ----------------------- | ---------------------------------------------- |
| `test_auth.py`          | Login, MFA, token refresh, logout              |
| `test_screening.py`     | Prediction endpoint                            |
| `test_models.py`        | Model creation and relationships               |
| `test_crypto.py`        | Encryption/decryption                          |
| `test_ml_engine.py`     | ML prediction pipeline                         |
| `test_doctor_isolation.py` | DOCTOR role data isolation                  |
| `test_analytics.py`     | Dashboard and reporting views                  |
| `test_fhir.py`          | FHIR R4 Bundle endpoint                        |
| `test_bulk_import.py`   | CSV bulk import                                |

### Issues

1. **Heavy use of mocks** — Most tests mock serializers, authenticate functions, and models rather than using Django's test client with a real database. This means the tests verify mock behavior, not actual application behavior. Integration tests with `APIClient` and a test database would be more valuable.

2. **No `conftest.py` DB fixtures** — The conftest provides sample CBC data but no model fixtures. The `django_db_setup` fixture overrides the DB engine to plain `postgresql` (not `django_tenants.postgresql_backend`), which means tenant-aware features cannot be properly tested.

3. **Frontend has minimal tests** — Only `App.test.js` exists. No component tests, no API integration tests, no E2E tests.

4. **No coverage enforcement** — The `test:ci` script has `--coverage` but there's no coverage threshold configured. CI will pass at 0% coverage.

---

## 7. Infrastructure Review

### Docker Compose

**Good:**
- Health checks on all services
- Proper `depends_on` with `condition: service_healthy`
- Volumes for persistent data (postgres, redis, static files)
- ML models mounted read-only
- Separate testing and production compose files

**Issues:**

- **No resource limits** — No `mem_limit`, `cpus`, or `deploy.resources` configured. A single container can consume all host memory.

- **Redis has no password** — The Redis instance runs without authentication. If the Docker network is compromised, Redis is fully accessible.

- **`celery_beat` has no locking** — Running `celery beat` without `--pidfile` or a distributed lock means that if two beat instances start (e.g., during deployment), tasks will be double-scheduled.

### CI/CD

**Good:**
- Tests run before build (backend + frontend)
- Docker images tagged with both `latest` and commit SHA
- Rollback on health check failure
- SSH-based deployment with proper key management

**Issues:**

- **No staging environment** — Code goes directly from `master` to production. The testing environment is on a different compose file but there's no CI pipeline that deploys to it first.

- **`docker-compose` (v1) used in deploy script** — The deploy script uses `docker-compose` (hyphenated, v1 syntax). Docker Compose V2 uses `docker compose` (space). V1 is deprecated.

- **No image vulnerability scanning** — No `trivy`, `grype`, or similar scanner in the pipeline.

---

## 8. Recommendations (Priority Order)

### Critical

1. **Fix `MFASettings.secret_key` max_length** — Change `CharField(max_length=32)` to `TextField()` to prevent Fernet ciphertext truncation.
2. **Remove password reset token from logs** — Gate on `DEBUG` or remove the `logger.info` call in `ForgotPasswordView`.
3. **Add authorization to `ConsentRevokeView`** — Verify the requesting user has permission over the consent's patient.
4. **Fix `CaseListView` filter-before-slice ordering** — Apply `.filter()` before `[:500]`.

### High

5. **Add a README** — Include setup instructions, architecture overview, and contribution guidelines.
6. **Add React ErrorBoundary** — Prevent full app crashes from unhandled component errors.
7. **Reduce access token lifetime** — From 60 minutes to 15 minutes to limit compromised token exposure.
8. **Protect OpenAPI docs in production** — Add authentication or disable `/api/docs/` and `/api/redoc/`.
9. **Add Redis authentication** — Set `requirepass` on the Redis instance.

### Medium

10. **Consolidate settings `prod`/`production` duplication** — Single conditional block.
11. **Add integration tests** — Replace mock-heavy unit tests with `APIClient`-based integration tests using a real test database.
12. **Add frontend component tests** — At minimum test the login flow, screening form, and role-based routing.
13. **Add container resource limits** — Prevent OOM scenarios.
14. **Optimize bulk import** — Batch DB operations for large CSV imports.
15. **Audit unused frontend dependencies** — Remove unused shadcn/ui components to reduce bundle size.

### Low

16. **Fix `Patient.unique_together`** — Use `unique=True` on the field instead.
17. **Add Docker Compose V2 syntax** — Replace `docker-compose` with `docker compose`.
18. **Add image vulnerability scanning to CI** — Integrate Trivy or similar.
19. **Use `Notification.type` as TextChoices** — For type safety.
20. **Remove cache-busting query parameter** — Use proper HTTP cache headers instead.

---

## 9. Summary

This is a well-architected healthcare platform with strong foundations in multi-tenancy, PHI protection, and compliance auditing. The JWT implementation with refresh token rotation is above average. The ML pipeline is well-structured with reproducibility hashing.

The main areas needing attention are: the MFA secret field truncation bug (critical), authorization gaps in consent revocation, test quality (too mock-heavy, no frontend tests), and a few production hardening items (Redis auth, resource limits, OpenAPI protection).

The codebase follows consistent patterns and naming conventions. The separation between core, screening, and analytics apps is clean. The FHIR R4 endpoint and bulk import features demonstrate good extensibility design.

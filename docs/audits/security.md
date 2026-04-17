# Security Audit (Full Repo)

## Executive summary

The codebase shows strong baseline hardening: PHI is Fernet-encrypted with MultiFernet rotation support, the audit chain is HMAC-signed with a sequence+prev_hash chain, webhooks verify HMAC-SHA256 with `hmac.compare_digest`, throttles fail-closed, and SSRF/private-IP protections are in place on outbound webhook delivery. Startup secret validation enforces distinct keys and minimum length in production. The main residual risks are **incomplete DOCTOR isolation on write paths** (a DOCTOR can attribute screenings to another doctor), **client-spoofable `X-Forwarded-For` on the webhook source-IP allowlist** (defence-in-depth only — HMAC is still primary), and a handful of medium-severity issues around password-setup email tokens, MFA EMAIL single-factor collapse, and the demo-seed backdoor. No critical/exploitable HIGH issues found that compromise auth, tenant isolation, or PHI confidentiality.

## Scope

- HEAD: `ab817d39e6bfa74eaf90ef7962922a18aa82c4b4`
- Categories scanned: auth & session; RBAC + tenant isolation; input validation/injection; PHI handling (crypto, logs, audit); billing/webhook; CORS/CSRF/clickjacking; secrets/config; dependency/CI; operational exposure (compose, nginx)
- Explicitly out of scope:
  - Diff-only audits of the last ~20 commits (previous agent already covered this)
  - Razorpay test-credential history exposure (already rotated, history rewritten)
  - Frontend XSS / SPA injection (server-side render is minimal; CSP is set at nginx)
  - Pen-testing / live exploit validation (Phase 4)

## Findings

### Finding 1: RBAC: DOCTOR can attribute screenings to a different doctor via `doctorId` on `/api/screening/predict`

- **Severity:** MEDIUM
- **Confidence:** 9/10
- **Location:** [backend_v3/apps/screening/views.py:245-247](backend_v3/apps/screening/views.py#L245), [backend_v3/apps/screening/views.py:86-88](backend_v3/apps/screening/views.py#L86)
- **Description:** `PredictView.required_roles = [Role.LAB, Role.DOCTOR]`. For a DOCTOR caller, the view resolves the doctor from the client-supplied `doctorId` field (`Doctor.objects.filter(code=data['doctorId']).first()`) without verifying that the lookup result belongs to the requesting user. Every other DOCTOR-reachable view (review, explain, trend, screening detail) correctly filters via `Doctor.objects.filter(email=request.user.email, is_active=True)`, so this is an isolated inconsistency. The PHI audit log still records the true `request.user.username`, but the Screening row's `doctor_id` FK points at whichever doctor the attacker chose — corrupting downstream "my cases" views and high-risk-alert routing for that doctor.
- **Exploit scenario:** Dr Alice (authenticated DOCTOR) POSTs a screening with `doctorId=<Dr Bob's code>`. The Screening row is attributed to Bob. Alice has now seeded Bob's `CaseStatsView`, `PatientTrendView`, and `ExplainView` with fabricated records, and if the result is high-risk the `send_high_risk_alert` email is delivered to Bob's inbox instead of (or in addition to) the real clinician.
- **Recommendation:** In `PredictView.post()` (or `_persist_screening`), when `request.user.role == Role.DOCTOR`, ignore any client-supplied `doctorId` and derive `doctor` from `Doctor.objects.filter(email=request.user.email, is_active=True)`. Reject the request with 403 if the derived doctor record is missing. `FHIRBundleView` has the same gap and needs the same treatment.

---

### Finding 2: RBAC: DOCTOR can read any patient's consent status via `/api/screening/consent/status/{patient_id}`

- **Severity:** MEDIUM
- **Confidence:** 8/10
- **Location:** [backend_v3/apps/screening/views.py:614-666](backend_v3/apps/screening/views.py#L614)
- **Description:** `ConsentStatusView.get()` only runs `_validate_lab_association(request.user)` which returns success for any DOCTOR with an active Doctor record. It then looks up `Patient.objects.get(patient_id=patient_id)` with no `referring_doctor` filter. A DOCTOR can therefore enumerate consent state for every patient in the tenant, including patients under other doctors. Consent metadata (exists / type / expiry) is lower-sensitivity than full PHI, but combined with Finding 1 it lets a malicious doctor map the tenant's patient population.
- **Exploit scenario:** A DOCTOR iterates patient IDs (often sequential or easily guessed lab-assigned identifiers) against `GET /api/screening/consent/status/{id}` and receives `hasConsent`/`consentedAt` for each, building a directory of active patients and their consent freshness.
- **Recommendation:** Apply the same `referring_doctor == current_user.doctor` check that `ReviewScreeningView` and `ExplainView` use, and return 403 otherwise. Alternatively, restrict the endpoint to `Role.LAB` only if DOCTORs don't need it.

---

### Finding 3: PHI: `FHIRBundleView` skips consent validation, DOCTOR isolation, and serializer-level CBC validation

- **Severity:** MEDIUM
- **Confidence:** 9/10
- **Location:** [backend_v3/apps/screening/views.py:1084-1275](backend_v3/apps/screening/views.py#L1084)
- **Description:** Three issues stack in this endpoint:
  1. No `consentId` is checked — a screening can be run against a patient with revoked/expired consent, bypassing the guard `PredictView._validate_consent` enforces.
  2. DOCTOR callers bypass the doctor-isolation check entirely (no scope to their own patients), and no `doctor` FK is set on the Screening row so the high-risk-alert path can't route to the right clinician.
  3. CBC values are read through `float(value_q['value'])` with no range validation — the `CBCSerializer`'s clinical bounds (Hb 1-30, etc.) apply only to the JSON path. A malicious payload can push the ML model with out-of-range inputs that may return nonsense classifications, and (worse) crash with `ValueError` if `value` is not float-coercible since the `try/except` only covers birthDate parsing.
- **Exploit scenario:** A DOCTOR posts a FHIR bundle for a patient they do not own, with a revoked consent on file. The screening is persisted anyway, the PHI audit log records `PHI_FHIR_PREDICT` but no consent-violation, and the tenant has no signal that an unauthorised clinician just queried that patient.
- **Recommendation:** Gate FHIR ingest behind the same `_validate_consent()` helper, enforce DOCTOR scoping, add range validation for every LOINC value before `float()`, and wrap the persistence in try/except that returns 422 on bad input rather than bubbling a 500.

---

### Finding 4: Auth: password-reset + password-setup tokens survive a password rotation

- **Severity:** MEDIUM
- **Confidence:** 8/10
- **Location:** [backend_v3/apps/core/views.py:794-849](backend_v3/apps/core/views.py#L794), [backend_v3/apps/core/views.py:852-906](backend_v3/apps/core/views.py#L852)
- **Description:** `ResetPasswordView` only invalidates refresh tokens after a successful reset — it does not invalidate any other outstanding reset tokens for the same user. Because `cache.set(f'pwd_reset_{token}', str(user.id), timeout=900)` uses a random token as key, a user (or attacker) who triggers two reset emails back-to-back has both tokens valid until their respective TTLs. Similarly, `SetPasswordView` uses `default_token_generator.check_token` whose validity is solely a function of the `last_login` + `password` hash — after a user sets their password via that link, the same token keeps working until `last_login` changes or the password is rotated again. A stolen invite email is therefore replayable until the first successful use triggers a `last_login` update, which only happens later on explicit login. If an attacker intercepts the admin-provisioning invite email (or finds it in a forwarded mailbox), they can race the legitimate user to claim the account.
- **Exploit scenario:** An internal IT person forwards a user-provisioning email to a helpdesk ticket. The ticket contents are later exposed through a logging pipeline or support query; an attacker extracts the `/set-password/<uid>/<token>` URL and claims the account before the real user has logged in.
- **Recommendation:** (a) In `ResetPasswordView`, on success, delete every cache entry matching `pwd_reset_*` keyed to that user_id — or switch to storing tokens in a database row with a `used_at` + user FK so invalidation is straightforward. (b) In `SetPasswordView`, invalidate `default_token_generator`-minted tokens by bumping `user.last_login` (or setting an `invite_accepted_at` field) in the same transaction as the password save.

---

### Finding 5: Secrets: demo-seed command writes hardcoded weak admin passwords with no env-guard

- **Severity:** MEDIUM
- **Confidence:** 9/10
- **Location:** [backend_v3/apps/core/management/commands/seed_demo_data.py:198-232](backend_v3/apps/core/management/commands/seed_demo_data.py#L198)
- **Description:** `seed_demo_data` unconditionally creates `superadmin` with password `SuperAdmin@2024`, and `lab_demo` / `doctor_demo` with `Demo@2024`. The command performs `is_crypto_ready()` and `APP_ENV` checks nowhere — nothing prevents it from being run against a live production DB. Anyone with shell access to the backend container (or a misfired deploy script) can create or reset a Django superuser with a known weak password in a single command. The seeded user has `is_superuser=True` and bypasses every permission class.
- **Exploit scenario:** Operator runs `python manage.py seed_demo_data --clean` in the wrong shell (prod, not staging). The command completes silently, the attacker-known credentials now log in as full platform superadmin, and the `--clean` flag has wiped real demo-namespace data.
- **Recommendation:** At the top of `Command.handle`, refuse to run when `settings.APP_ENV in ('production', 'prod', 'staging')` unless `FORCE_DEMO_SEED=1`. Better: generate passwords with `secrets.token_urlsafe(16)` and print them once to stdout — never hardcoded.

---

### Finding 6: Auth: MFA auto-migration silently downgrades TOTP to email, reducing MFA to email-only

- **Severity:** MEDIUM
- **Confidence:** 8/10
- **Location:** [backend_v3/apps/core/views.py:247-253](backend_v3/apps/core/views.py#L247), [backend_v3/apps/core/mfa.py:268-278](backend_v3/apps/core/mfa.py#L268)
- **Description:** On every login, if the user's `mfa_settings.mfa_method == TOTP`, the code silently migrates them to EMAIL (`MFAManager.migrate_totp_to_email`) and discards the TOTP `secret_key`. From that point the user's "MFA" is equivalent to "can read their email" — which for LAB/DOCTOR roles is very often the same mailbox used to receive support forwards and password resets. Effectively the second factor collapses into the same factor as the password reset flow: control of the inbox. This is a product decision, but it's undocumented in the runbook and there's no user consent or notification that their strong TOTP factor was removed. The `mfa_migrated` response flag is cosmetic — by the time the client sees it, the TOTP secret is already gone.
- **Exploit scenario:** An employee had a TOTP app on their phone (separate device). Employee leaves, someone later compromises their email (e.g. persistent OAuth token, mailbox forwarding rule). On the next login attempt, TOTP is silently stripped — the attacker can now log in using only the hijacked email to receive the OTP. Previously they would have been blocked by the TOTP factor.
- **Recommendation:** Either (a) preserve TOTP and treat EMAIL as a secondary recovery factor rather than a replacement, or (b) require an additional confirmation step (enter current TOTP code once before switching to EMAIL). At minimum, send an email to the user's address-on-file alerting them that MFA was downgraded.

---

### Finding 7: Auth: refresh-token rotation is not atomic under concurrent requests

- **Severity:** LOW
- **Confidence:** 8/10
- **Location:** [backend_v3/apps/core/authentication.py:231-278](backend_v3/apps/core/authentication.py#L231)
- **Description:** `refresh_tokens()` reads the `RefreshToken` row without `select_for_update`, checks `is_revoked`, then updates `is_revoked=True` and mints new tokens. Two concurrent requests with the same refresh token both pass the `is_revoked=False` check, both succeed, and both mint new access+refresh pairs. The old token is still marked revoked at the end, but two usable refresh chains now exist in parallel. The token-reuse-detection branch (line 260-263) correctly revokes the whole chain if a *known-revoked* token is re-presented, but the race window itself produces valid duplicate chains that are never detected.
- **Exploit scenario:** A race-condition-aware attacker with a stolen refresh token can split the session: fire two concurrent refresh requests from different processes, both accept. Now both the legitimate client and the attacker have valid refresh chains; neither chain triggers the reuse-detection because the original token is (correctly) marked revoked once, not twice.
- **Recommendation:** Wrap the lookup/revoke/mint block in `transaction.atomic()` with `select_for_update()` on the `RefreshToken` row, or use `.filter(...is_revoked=False).update(is_revoked=True)` and check the updated-row-count to decide whether the caller won the race.

---

### Finding 8: Webhook: client-controlled `X-Forwarded-For` can spoof Razorpay source IP

- **Severity:** LOW
- **Confidence:** 9/10
- **Location:** [backend_v3/apps/billing/views.py:159-166](backend_v3/apps/billing/views.py#L159)
- **Description:** `_client_ip()` uses the first value of `X-Forwarded-For` when present. Nginx sets `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for`, which **appends** the real client's IP to any client-supplied XFF header rather than replacing it. A direct HTTP client can therefore send `X-Forwarded-For: 52.66.143.197` (a Razorpay IP) and `_client_ip()` will return that value, passing `_is_razorpay_ip()`. HMAC-SHA256 signature verification is still required on the next step, so this isn't exploitable in isolation — but it defeats the "defence in depth" purpose of the IP allowlist, and is misleading in the comment ("trusting X-Forwarded-For only when behind nginx"). The same pattern exists in `apps/core/audit.py:47-51`, where a spoofed XFF is written into the audit log's `ip_address` column.
- **Exploit scenario:** An attacker with the Razorpay webhook secret (say, exfiltrated via log scraping or backup exposure) sends a forged `subscription.cancelled` event with spoofed `X-Forwarded-For`. The IP allowlist is bypassed; the HMAC check is the last line. In the audit log, the attacker's actions appear as originating from a legitimate Razorpay IP.
- **Recommendation:** Parse XFF from the right, taking the *last* entry before a known-trusted nginx proxy hop. Django's `SECURE_PROXY_SSL_HEADER` pattern and DRF's throttle `get_ident()` use `REMOTE_ADDR` plus one pop from XFF — port that logic. Better, configure nginx to replace (not append) XFF via `proxy_set_header X-Forwarded-For $remote_addr;` at the edge server block.

---

### Finding 9: Webhook outbound: DNS-rebinding guard pins resolved IP but breaks TLS SNI/cert validation

- **Severity:** MEDIUM
- **Confidence:** 7/10
- **Location:** [backend_v3/apps/billing/tasks.py:799-864](backend_v3/apps/billing/tasks.py#L799)
- **Description:** `deliver_webhook()` resolves DNS once, pins the first safe IP, and builds the delivery URL as `https://<ip>:<port><path>` while passing `Host: <original hostname>` in the headers and `verify=True`. The intent (prevent TOCTOU DNS rebinding) is correct, but `requests` performs TLS certificate verification against the URL's host component (the IP), not the `Host` header. Most CA-issued certificates do not contain the server's IP in `subjectAltName`, so the TLS handshake should fail with `SSLCertVerificationError`. Either (a) all current test webhooks are hitting servers that happen to have IP SANs — unlikely at scale — or (b) `verify=True` is being silently overridden upstream, in which case DNS-rebinding protection is effectively a denial-of-service for legitimate endpoints plus unverified TLS to the pinned IP. The fallback should use the hostname in the URL and pin the IP via a custom `HTTPAdapter`/`urllib3.PoolManager` so SNI + cert validation work against the hostname.
- **Exploit scenario:** Customer registers `https://hooks.example.com/...` with a valid cert. On the first webhook delivery, DNS resolves to `203.0.113.5`. `requests.post('https://203.0.113.5:443/...', verify=True)` fails cert verification (hostname mismatch) and the webhook never fires — the tenant loses real-time events. Alternatively, if `verify=True` is silently disabled or bypassed for IPs, an attacker who controls BGP between Clinomic and the customer can MITM the pinned-IP session undetected.
- **Recommendation:** Resolve DNS once, validate the IP against the SSRF allowlist, then pass the original hostname URL to `requests` with a mounted `HTTPAdapter` that forces `urlopen` to dial the pre-validated IP. That preserves cert validation + SNI. See `requests_toolbelt.adapters.host_header_ssl.HostHeaderSSLAdapter` for reference.

---

### Finding 10: Operational: `docker-compose.prod.yml` mounts `nginx.testing.conf` (not `nginx.prod.conf`) as the production nginx config

- **Severity:** MEDIUM
- **Confidence:** 10/10
- **Location:** [docker-compose.prod.yml:185](docker-compose.prod.yml#L185)
- **Description:** The `nginx` service in the production compose file mounts `./nginx.testing.conf:/etc/nginx/nginx.conf:ro`, not `nginx.prod.conf`. `nginx.testing.conf` has several different directives than the hardened `nginx.prod.conf`: it includes a `testing.clinomiclabs.com` vhost, it is missing the `/admin/ limit_req zone=admin_limit` rate limit, it is missing the `/metrics` internal-ACL (it just `deny all; return 404;` which is fine but inconsistent), and its CSP allows `script-src 'unsafe-inline'` which `nginx.prod.conf` does not. So every "prod-only" hardening in `nginx.prod.conf` is currently dead code — the live nginx is running the testing config.
- **Exploit scenario:** The prod CSP is weaker than intended (permits inline script), and the Django `/admin/` path is not rate-limited at the edge. A credential-stuffing attacker targeting `/admin/login/` gets only the Django-level login throttle (5/min) rather than the nginx `admin_limit` (2 r/s burst 5) layer that `nginx.prod.conf` defines.
- **Recommendation:** Either (a) change line 185 to `./nginx.prod.conf:/etc/nginx/nginx.conf:ro` and reconcile any testing-vhost needs into a separate config, or (b) delete `nginx.prod.conf` and accept `nginx.testing.conf` as the single source of truth while porting its missing hardening (admin rate limit, stricter CSP) into it. Add a CI check that diffs the two to prevent drift.

---

### Finding 11: CI: test secrets committed in workflow — low-entropy, production-style names

- **Severity:** LOW
- **Confidence:** 9/10
- **Location:** [.github/workflows/production-deploy.yml:50-53](.github/workflows/production-deploy.yml#L50)
- **Description:** The production deploy workflow exports hardcoded secrets named `DJANGO_SECRET_KEY`, `JWT_SECRET_KEY`, `JWT_REFRESH_SECRET_KEY`, `AUDIT_SIGNING_KEY` with literal string values like `ci-secret-key-not-for-production`. These are only used by the `test-backend` job, and `APP_ENV=testing` in the same block means the production secret-validation path is not exercised. So production startup is never validated by CI with the real strict checks — regressions in `validate_required_secrets` only surface at deploy time. The committed values are also short (`<50` chars) and will be flagged by any downstream secret-scanner as potential leaks.
- **Exploit scenario:** Not directly exploitable (these are CI-only test values). Operational risk: a regression that weakens production secret validation passes CI silently.
- **Recommendation:** Generate 64-char random values with `python -c "import secrets;print(secrets.token_urlsafe(48))"` at job start, and add a separate `test-production-startup` job that runs `DJANGO_SETTINGS_MODULE=clinomic.settings APP_ENV=production python manage.py check --deploy` to smoke-test the strict validator.

---

### Finding 12: Config: `.env.example` references `JWT_REFRESH_SECRET_KEY` but settings.py never reads it

- **Severity:** LOW
- **Confidence:** 10/10
- **Location:** [backend_v3/.env.example:39](backend_v3/.env.example#L39), [backend_v3/clinomic/settings.py:242-251](backend_v3/clinomic/settings.py#L242)
- **Description:** `.env.example` instructs operators to set a separate `JWT_REFRESH_SECRET_KEY`, and the docker-compose files pass that variable through, but `authentication.py` and `settings.py` only ever use `JWT_SECRET_KEY` for both access and refresh tokens. Refresh tokens are signed with the same key as access tokens. Additionally, `.env.example:57` says `MFA_REQUIRED_ROLES=ADMIN,DOCTOR` — but the ADMIN role was removed in migration `0007_remove_admin_role`, so a fresh-from-example env produces `MFA_REQUIRED_ROLES=['ADMIN', 'DOCTOR']` which silently drops MFA enforcement for LAB users (since `ADMIN` doesn't exist anymore). An operator following the docs ends up with weaker-than-expected MFA enforcement.
- **Exploit scenario:** Operator sets `MFA_REQUIRED_ROLES=ADMIN,DOCTOR` from the example. LAB users — the organisation admins who manage all tenant data — bypass MFA entirely because `LAB not in ('ADMIN', 'DOCTOR')`.
- **Recommendation:** Remove `JWT_REFRESH_SECRET_KEY` from `.env.example` and `docker-compose.prod.yml`, or actually implement refresh-token signing with a distinct key in `create_refresh_token` / `decode_token`. Fix the example's `MFA_REQUIRED_ROLES` to `LAB,DOCTOR,SUPER_ADMIN` to match the current Role enum.

---

### Finding 13: Webhook: `_handle_subscription_activated` changes the plan from webhook payload with no prior correlation check

- **Severity:** LOW
- **Confidence:** 7/10
- **Location:** [backend_v3/apps/billing/views.py:206-215](backend_v3/apps/billing/views.py#L206)
- **Description:** On `subscription.activated`, the handler looks up `SubscriptionPlan.objects.filter(razorpay_plan_id=rz_plan_id).first()` and assigns it to the tenant's subscription, *overriding* whatever plan was previously associated. This is correct for the happy path (upgrade flow where `AdminBillingUpgradeView` stored the new `razorpay_sub_id`), but if an attacker ever obtains a valid signed webhook (e.g. via replay from a leaked log, or a separately-compromised webhook secret) they can force a plan downgrade by sending `subscription.activated` with a `plan_id` pointing at the cheapest plan. There's no check that the incoming plan matches what the tenant admin actually requested. Idempotency via `PaymentEvent.razorpay_event_id` prevents true replays, but a newly-captured event-id is not constrained. This is rated LOW because it requires prior webhook secret compromise; defence-in-depth suggests adding the check.
- **Exploit scenario:** Attacker who has leaked the `RAZORPAY_WEBHOOK_SECRET` (e.g. via an `.env` leak on a compromised build agent) crafts a signed `subscription.activated` payload with a `plan_id` pointing at the free-tier plan, and the target tenant is silently downgraded at next webhook arrival window.
- **Recommendation:** Before changing `sub.plan`, verify `rz_plan_id` matches the currently-expected plan (e.g. what `AdminBillingUpgradeView` recorded) or at minimum require that the incoming plan is of equal-or-higher price. Log at WARN level when a webhook attempts to change plans without a pending upgrade record.

---

### Finding 14: PHI: CSV bulk-import parses the full payload into memory before tenant-scope checks

- **Severity:** LOW
- **Confidence:** 7/10
- **Location:** [backend_v3/apps/screening/views.py:957-1035](backend_v3/apps/screening/views.py#L957)
- **Description:** `BulkImportView.post()` reads the whole CSV into `raw_bytes` (capped at 10 MB), decodes UTF-8-with-BOM, and passes the raw text to `process_bulk_import.delay(str(job.id), csv_text, lab_code, request.user.username)` — i.e. the CSV body is serialised into the Celery broker (Redis) payload. Every row's patient PII sits in Redis as a task argument, in plaintext, until the worker processes it. `CELERY_TASK_STORE_ERRORS_EVEN_IF_IGNORED = True` means any task failure persists the task payload to the result backend. For a 10 MB CSV this is tens of thousands of patient rows in a cache Redis instance that is less-tightly access-controlled than the Postgres PHI tables.
- **Exploit scenario:** A Redis backup (or `MONITOR` by an over-privileged ops user) captures Celery task arguments containing unencrypted patient identifiers, names, ages, and CBC values.
- **Recommendation:** Write the CSV to a tenant-scoped S3 bucket (server-side encrypted) or the DB in a dedicated import-payload table, and enqueue only the job_id + storage reference. Have the worker stream-read the rows server-side. Additionally, never stash `csv_text` in `task.kwargs` where it can land in the result backend on failure.

---

### Finding 15: PHI: `name_encrypted` can be empty-string but `age_encrypted`/`sex_encrypted` are always encrypted — inconsistency hides PHI in error paths

- **Severity:** LOW
- **Confidence:** 7/10
- **Location:** [backend_v3/apps/screening/views.py:585-595](backend_v3/apps/screening/views.py#L585), [backend_v3/apps/screening/models.py:82-84](backend_v3/apps/screening/models.py#L82)
- **Description:** In `ConsentRecordView` and `BulkImportView`, `Patient.objects.get_or_create(...)` stores `name_encrypted=''` (literal empty string, not a Fernet token) while `age_encrypted` and `sex_encrypted` are always passed through `encrypt_field`. `Patient.name` getter uses `decrypt_field(self.name_encrypted)` which short-circuits on empty string and returns `''`. That's fine for reads, but any code path that tests `patient.name_encrypted.startswith('gAAAAA')` (a Fernet ciphertext prefix) to identify encrypted rows will mis-classify these empty-string rows. More concretely, if an attacker can insert a row whose `name_encrypted` field contains arbitrary plaintext (via a bug in the write path), the getter's `decrypt_field` will raise `CryptoError` and the property currently returns the sentinel `'[decryption error]'` — but there's no alarm / metric, so tampering is invisible.
- **Exploit scenario:** A misconfigured migration or partial rotation leaves `name_encrypted` fields with stale ciphertext. Reads silently return `'[decryption error]'` and nobody notices until a regulator asks for a patient's record and it's gone.
- **Recommendation:** Standardise: always store `encrypt_field('')` (which returns `''` anyway per current crypto.py, but the model layer should guarantee that every non-null field is either empty or a valid Fernet token). Emit a Prometheus counter `phi_decrypt_errors_total` when `Patient.name`/`.age`/`.sex` hit the `CryptoError` branch so ops see tampering signals.

---

## What's already done well

- **Secret validation on boot** (`validate_required_secrets`) rejects missing, short, or well-known placeholder values, and enforces that `JWT_SECRET_KEY != DJANGO_SECRET_KEY` in production.
- **Fernet + MultiFernet rotation** is correctly implemented with `PREVIOUS_ENCRYPTION_KEYS` support and a dedicated `rotate_encryption_keys` management command.
- **JWT decode** requires `iss`/`aud`/`exp`/`sub`/`jti`/`token_type`, disallows algorithm confusion via explicit `algorithms=[JWT_ALGORITHM]`, and runs a token-type check post-decode.
- **JWT blacklist fails closed** (503 on Redis outage) rather than silently allowing revoked tokens through.
- **Throttles fail closed** via `_FailClosedMixin` — Redis outage doesn't disable rate limiting.
- **Webhook HMAC** uses the Razorpay SDK's `verify_webhook_signature` on the raw body (not parsed JSON), and `PaymentVerifyView` uses `hmac.compare_digest` on the signature comparison. Webhook rows are dedup'd via `PaymentEvent.razorpay_event_id`.
- **Outbound webhook SSRF protection**: HTTPS-only, block private/loopback/reserved/link-local, pin-resolved-IP (Finding 9 nitpicks the implementation but the intent is correct).
- **Audit log chain**: sequence + previous_hash + SHA-256 entry hash + HMAC signature, row-locked on write — tamper-evident.
- **MFA OTP comparison** uses `hmac.compare_digest`; OTP and cooldown have separate cache keys; backup codes are SHA-256 hashed.
- **Refresh token reuse detection** correctly revokes the whole chain if an already-revoked token is re-presented (Finding 7 is about the race before revocation, not after).
- **WebSocket auth** via first-message JWT (not in URL) — token doesn't leak into nginx logs or browser history. Requires `mfa_verified=true` + active user + valid tenant.
- **Tenant isolation at schema level** via `django-tenants` + `JWTTenantMiddleware` override; `X-Org-Id` header is only honoured when the JWT claims `is_super_admin=True` and the JWT-resolved org is the public schema.
- **Prod container hardening**: `read_only: true`, `tmpfs: /tmp`, `no-new-privileges`, resource limits per service, Grafana `GF_USERS_ALLOW_SIGN_UP=false`, prometheus `/metrics` ACL'd to private CIDRs in `nginx.prod.conf` (Finding 10 notes the prod config isn't actually deployed).
- **Cryptographic hygiene**: `secrets.token_urlsafe` for API keys / trusted-device / reset tokens; API keys stored only as SHA-256 digests with scope enforcement; trusted-device cookies are IP-bound.
- **CSRF + CORS**: `CORS_ALLOWED_ORIGINS` derived from `FRONTEND_URL` env, `CORS_ALLOW_CREDENTIALS=True` is only paired with an explicit origin list (no wildcard), `CSRF_COOKIE_SECURE` and `SESSION_COOKIE_SECURE` are true in production, `X_FRAME_OPTIONS=DENY`, HSTS 1 year.
- **Password validation**: min length 12, similarity/common/numeric validators.

## Residual risks the team is knowingly accepting

- **Login throttle at 5/min per IP** — documented in RUNBOOK. Behind a corporate NAT or shared egress IP, legitimate users may hit the throttle faster than bad actors.
- **Sync tenant creation** in `PlatformCreateOrgView` runs migrations inline — a long signup holds the request thread, but the alternative (async) complicates tenant-ready semantics.
- **`APP_ENV` IP-allowlist bypass**: `_is_razorpay_ip` auto-returns True in `dev/testing/development` environments. Intentional, documented.
- **`PlanLimitMiddleware` fails open** on cache/DB errors (documented in-code) rather than 402 every paying customer during a Redis blip.
- **Webhook 503 on lock contention** relies on Razorpay retries — accepted because the alternative (serialise with a big lock) would increase latency.
- **Login errors intentionally generic** ("Invalid credentials") — user enumeration via timing is a theoretical residual risk; the throttle caps its practical exploitation.

## Recommended next pass

1. **Pen-testing pass** on the DOCTOR role specifically: walk through every `required_roles = [..., Role.DOCTOR]` view and confirm doctor-scoping is actually enforced on every write + read path. Findings 1-3 suggest this class of bug may recur.
2. **Secret scanning in CI** via `gitleaks` or `trufflehog` — catch future leaks of the kind history was recently rewritten to remove.
3. **Audit-chain verification tool**: build a management command that walks `AuditLogEntry` from sequence=1 and validates each `entry_hash` + `signature`. Run nightly. No such verifier exists yet; the chain is only tamper-*evident* if someone looks.
4. **Redis password rotation drill**: test that rotating `REDIS_PASSWORD` without downtime works end-to-end (backend + workers + channels + celery-beat). The current compose hard-codes the password into every service env.
5. **DB role least-privilege rollout** (`POSTGRES_APP_USER`): per the comment in `ensure_app_role.py` this is not yet flipped in production. Plan the cutover.
6. **Dependency pinning audit**: `scikit-learn>=1.4,<1.5` and `setuptools>=69,<70` are pinned to work around known issues — track those constraints explicitly in a TODO so they don't linger indefinitely.
7. **Consent-renewal UX**: Finding 3 aside, the current consent model doesn't have a "renew" flow — expired consents require a fresh record. Confirm that's the desired semantics.

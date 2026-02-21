# Develop Branch — Comprehensive Code Review

**Date:** 2026-02-20
**Branch reviewed:** `develop` (merged into `claude/review-codebase-RcqD6`)
**Scope:** All 56 changed files (~5,500 lines added) across Phases 1–3

---

## Executive Summary

The `develop` branch implements **Phase 1 (critical bug fixes), Phase 2 (SaaS billing engine), and Phase 3 (clinical intelligence + real-time)** from the upgrade roadmap. The implementation is structurally sound and covers the intended feature set, but the review uncovered **12 critical/high vulnerabilities, 18 medium-severity issues, and 37 lower-priority quality/UX gaps** that must be addressed before production deployment.

The most severe finding: **WebSocket code exists but cannot work** — both Docker Compose files still use WSGI (gunicorn), and nginx has no WebSocket proxy configuration.

---

## Issues by Severity

### CRITICAL (Must fix before any deploy)

| # | Issue | File(s) | Description |
|---|-------|---------|-------------|
| C1 | **WebSocket dead on arrival** | `docker-compose.*.yml`, `nginx.*.conf` | Backend runs `gunicorn clinomic.wsgi:application` (WSGI). Django Channels requires ASGI (`uvicorn`/`daphne`). Nginx has zero WebSocket config — no `Upgrade` header handling, no `/ws/` proxy. All WebSocket features (work queue updates, doctor alerts) are non-functional. |
| C2 | **Signup has no transaction wrapping** | `billing/views.py:88-130` | Creates Organization → Domain → User → Subscription sequentially without `@transaction.atomic`. If User creation fails, orphaned Organization + PostgreSQL schema remain with no cleanup path. |
| C3 | **Signup race condition (TOCTOU)** | `billing/views.py:78-93` | `exists()` check then `create()` is a classic time-of-check/time-of-use race. Two concurrent signups with the same name both pass uniqueness checks, second crashes with unhandled `IntegrityError` (500 to user). |
| C4 | **Expired JWT sets tenant context** | `billing/middleware.py:35-41` | `JWTTenantMiddleware` decodes JWT with `verify_exp: False`. An expired token still switches `connection.set_tenant()`. All middleware running after (PlanLimitMiddleware, AuditlogMiddleware) executes in the wrong tenant's context before DRF rejects the request. |
| C5 | **Tenant isolation bypass on WebSocket** | `screening/middleware.py:67-73`, `consumers.py:42` | Missing `org_id` in JWT causes silent fallback to `'public'` schema group. Any user without `org_id` joins `wq_public` and receives cross-tenant broadcast messages. |
| C6 | **Reserved schema name injection** | `billing/views.py:43-47` | `_slugify_org("Public")` → schema `public`. No blocklist for `public`, `pg_catalog`, `information_schema`. Could corrupt the shared schema. |

### HIGH (Fix before release/staging)

| # | Issue | File(s) | Description |
|---|-------|---------|-------------|
| H1 | **Webhook accepts forged events when secret not set** | `billing/views.py:173-186` | If `RAZORPAY_WEBHOOK_SECRET` is empty (default in `.env.example`), signature verification is entirely skipped. Attacker can forge `subscription.activated` to give any tenant unlimited access. |
| H2 | **No password validation on signup** | `billing/serializers.py:43` | `min_length=8` only. Django settings require 12 chars + complexity. `ResetPasswordView` enforces the full rules — inconsistency. |
| H3 | **No password validation on admin user create** | `core/views.py:688-710` | `AdminUserListView.post()` and `AdminUserDetailView.patch()` call `set_password()` without `validate_password()`. Admins can create accounts with trivial passwords. |
| H4 | **MFA bypass at signup** | `billing/views.py:131` | New admin gets JWT with `mfa_verified=True` without ever setting up MFA. All MFA-protected endpoints accessible immediately. |
| H5 | **PHI in work queue response** | `screening/views.py:477` | `WorkQueueView` returns `patientName` (decrypted PHI) in list endpoint. Every LAB/ADMIN user sees all patient names. Undermines encryption-at-rest design. |
| H6 | **Internal exceptions leaked to API** | `screening/views.py:116` | `str(e)` in PredictView error response can expose file paths, model loading errors, database strings. |
| H7 | **Non-atomic billing rollup** | `billing/tasks.py:66-90` | `compute_monthly_rollups` reads count, then resets to 0 — without `select_for_update`. An `increment_usage` firing between read and reset is permanently lost. |
| H8 | **`/onboarding` route has no role guard** | `frontend/App.js:234` | Any authenticated user (LAB, DOCTOR) can navigate to `/onboarding` and create labs, doctors, users. Must restrict to ADMIN. |
| H9 | **JWT token exposed in WebSocket URL** | `frontend/useWebSocket.js:38` | Access token passed as `?token=...` query parameter — visible in server logs, browser history, proxy logs. |

### MEDIUM

| # | Issue | File(s) | Description |
|---|-------|---------|-------------|
| M1 | **Settings `production`/`prod` duplication** | `settings.py:249-270` | Security headers block copy-pasted for both `APP_ENV` values. Should be `if APP_ENV in ('production', 'prod'):`. |
| M2 | **Redis DB collision** | `settings.py` | Channels and Celery both use Redis DB 0. Key namespace collision risk. Channels should use DB 2. |
| M3 | **.env.example missing new vars** | `.env.example` | `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `BASE_DOMAIN` not documented. |
| M4 | **PlanLimit cache bypass** | `billing/middleware.py:100-115` | 5-minute cache window allows burst over-usage. Fails open (allows requests) on DB error and caches that result for 5 min. |
| M5 | **PlanLimit path matching fragile** | `billing/middleware.py:90-93` | Trailing slash, URL encoding, case differences bypass the frozenset check. |
| M6 | **No DB index on `razorpay_sub_id`** | `billing/models.py:73` | Webhook lookups do full table scan. Also `blank=True` without `unique=True` allows duplicates. |
| M7 | **Thread-safety race in ML singleton** | `screening/ml_engine.py:296-312` | `get_ml_engine()` check-then-act on global without lock. Concurrent cold starts load models twice. |
| M8 | **SHAP computed on every prediction** | `screening/ml_engine.py:264` | ~100ms overhead per call. `TreeExplainer` reinstantiated every time instead of cached. Kills bulk import performance. |
| M9 | **Narrative trend off-by-one** | `narrative_engine.py:176-182` | Generated before screening is persisted, so `previous[0]` is actually the prior screening. Most recent historical data point incorrectly excluded from trend. |
| M10 | **Non-deterministic hash** | `screening/views.py:161-166` | `f"{cbc}"` uses `dict.__repr__()`. Key order could differ between API and FHIR ingestion. Use `json.dumps(sort_keys=True)`. |
| M11 | **No Celery retry config** | `billing/tasks.py` | Neither task has `max_retries`, `retry_backoff`, or `acks_late`. Failed increments = lost billing data. |
| M12 | **No email integration** | `core/views.py:563` | `ForgotPasswordView` has `# In production, send email here` comment. No actual email sending. |
| M13 | **Inconsistent admin route patterns** | `core/urls.py`, `screening/urls.py`, `billing/urls.py` | Core: `/api/admin/users`, Screening: `/api/screening/admin/labs`, Billing: `/api/billing/admin/usage`, Frontend: `/portal/*`. |
| M14 | **No subscription status transition enforcement** | `billing/models.py` | Any status can transition to any other. `CANCELLED` → `TRIAL` is possible via code. |
| M15 | **Upgrade without payment** | `billing/views.py:337-367` | `AdminBillingUpgradeView` changes plan in DB without Razorpay checkout. Comment says "scaffold" but it's wired to a live endpoint. |
| M16 | **Token refresh race in frontend** | `frontend/api.js:47-58` | 5 concurrent 401s fire 5 refresh requests. Need a mutex/queue so only one refreshes. |
| M17 | **`getBadge` defaults to DEFICIENT** | `frontend/ResultPanel.js:55` | Unknown label renders as "High Risk" — unsafe medical default. Should render as "Unknown/Indeterminate". |
| M18 | **Consent error swallowed** | `frontend/api.js:164-170` | `ConsentService.getStatus` catches all errors and returns `{hasConsent: false}`. Network errors block all screenings. |

### LOW / UX / Quality (37 items)

<details>
<summary>Click to expand</summary>

**Frontend:**
- No tests for any of the 7 new admin views, Signup, or Onboarding
- No error states — failed fetches show "No items found" silently
- No confirmation dialogs for destructive actions (deactivate user, delete lab/doctor, plan upgrade)
- No pagination in any admin list
- No search/filter on admin lists
- No reactivation capability (deactivate is one-way)
- Modal component duplicated in 3 files — extract to shared component
- 18 `useState` calls in Onboarding — consolidate with `useReducer`
- All icon-only buttons lack `aria-label` (accessibility)
- Modals lack focus trapping, Escape-to-close, `role="dialog"` (accessibility)
- SHAP chart tooltip shows no actual feature values (clinicians need "MCV = 78.3 fL")
- `shapLoading` state tracked but never rendered
- Onboarding has no back button
- Selection state lost on page refresh (not persisted to URL params)
- Enterprise plan allows direct signup — should route to Contact Sales
- Admin sidebar has duplicate "Labs" and "Doctors" labels
- No loading skeletons — all "Loading..." is plain text
- WebSocket reconnects on every token refresh even if token unchanged
- Notification polling at 60s exists alongside WebSocket — redundant
- `handleLogout` doesn't use try/finally — failed logout API call leaves user stuck
- Cache-busting `?r=` parameter on every request breaks HTTP caching

**Backend:**
- No tests for `JWTWebSocketMiddleware` — zero coverage on most security-critical WS component
- `schema_name` exposed in signup response — internal detail leaked
- Superusers bypass role check but then get 400 (no org) — inconsistent
- No heartbeat/revalidation on long-lived WebSocket connections
- Dead code: `deficient_default` template unreachable in narrative engine
- SHAP value 0.0 mislabeled as `risk_decreasing` — should be `neutral`
- Deprecated `asyncio.get_event_loop()` in ml_engine.py
- `ws_broadcast.py` shares mutable message dict across two group_send calls
- Thread-local schema in async context (`ws_broadcast.py:16`) — may read wrong tenant
- `period_end` Date vs DateTime type inconsistency in billing
- No idempotency guard on `increment_usage` — Celery at-least-once delivery causes double count
- Inconsistent trailing slashes in billing URLs
- No rate limiting on webhook endpoint
- Celery Beat has no distributed lock — rolling deploy fires tasks twice
- No Terms of Service / Privacy Policy consent on signup

</details>

---

## Configuration & Infrastructure Gaps

| Gap | Impact | Fix |
|-----|--------|-----|
| Both Docker Compose files use WSGI (`gunicorn`) | WebSocket completely non-functional | Switch to `uvicorn clinomic.asgi:application --host 0.0.0.0 --port 8000 --workers 4` |
| nginx has no WebSocket proxy config | WS connections fail at reverse proxy | Add `location /ws/ { proxy_pass ...; proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; }` |
| `.env.example` missing Razorpay + Channels vars | Fresh deploys misconfigured | Add `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `BASE_DOMAIN` |
| Redis DB 0 shared by Celery + Channels | Key collision risk | Give Channels its own DB (e.g., `/2`) |
| No `daphne` or Channels worker in Docker | Channel layer receives but no worker processes WS | Add Channels worker service or use `uvicorn` which handles both HTTP + WS |
| Settings duplication (`production`/`prod`) | Maintenance hazard | Consolidate to `if APP_ENV in ('production', 'prod'):` |

---

## Recommended Fix Priority

### P0 — Before Any Deploy (Critical)
1. Wrap SignupView in `transaction.atomic()` + catch `IntegrityError`
2. Block reserved schema names (`public`, `pg_catalog`, `information_schema`)
3. Verify JWT expiry in `JWTTenantMiddleware` (remove `verify_exp: False`)
4. Reject WebSocket connections without valid tenant (don't fallback to `public`)
5. Fail closed on missing webhook secret
6. Switch Docker to ASGI (uvicorn) + add nginx WebSocket proxy

### P1 — Before Staging/Testing
7. Add `validate_password()` to signup + admin user create
8. Remove PHI (`patientName`) from work queue response
9. Return generic error messages from PredictView
10. Add `select_for_update()` to billing rollup task
11. Add role guard to `/onboarding` route
12. Move JWT out of WebSocket query parameter
13. Fix `getBadge` medical default to neutral/unknown

### P2 — Before Production Release
14. Fix narrative trend off-by-one (persist screening before generating narrative)
15. Add thread-safe locking to ML singleton
16. Make SHAP computation opt-in (skip for bulk imports)
17. Use `json.dumps(sort_keys=True)` for deterministic hashing
18. Add confirmation dialogs for destructive actions
19. Add Celery retry configuration to billing tasks
20. Add token refresh deduplication in frontend
21. Update `.env.example` with new variables
22. Fix settings `production`/`prod` duplication
23. Add `db_index=True` to `razorpay_sub_id`

### P3 — Quality & Polish
24. Add frontend error states and retry buttons
25. Add pagination to admin lists
26. Extract shared Modal component
27. Add accessibility attributes (aria-label, focus trap)
28. Add tests for JWTWebSocketMiddleware
29. Add frontend tests for new views
30. Email integration (SendGrid/SES)
31. Unify admin API route pattern

---

## What's Still Not Built (Phases 4-5 from Roadmap)

- SSO (SAML/OIDC) for enterprise tenants
- SOC 2 Type II compliance tooling
- HL7 v2 ingestion for legacy lab systems
- FHIR Subscriptions (push-based)
- Population health analytics
- Kubernetes migration + horizontal scaling
- Read replicas / PgBouncer connection pooling
- ML model registry / A/B testing
- Mobile-responsive views / PWA
- Clinical validation study publication
- FDA/CE regulatory pathway assessment

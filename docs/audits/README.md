# Audit Reports — Clinomic B12 Screening SaaS

Three independent audit passes run on 2026-04-17 against HEAD `ab817d3` (post history-rewrite). Each report is self-contained and cites file:line for every claim.

## Files

| File | Scope | Findings |
|---|---|---|
| [security.md](security.md) | Full-repo security audit: auth, RBAC, tenant isolation, PHI handling, billing webhooks, injection, CORS, secrets, operational exposure | **0 HIGH / 10 MEDIUM / 5 LOW** |
| [production-seamlessness.md](production-seamlessness.md) | Day-2 ops: deploy path, failure recovery, scaling cliffs, observability, backup/DR, runbook quality, tenant isolation under stress, config drift | **25 total: 4 critical / 14 important / 7 nice-to-have** |
| [user-seamlessness.md](user-seamlessness.md) | End-to-end user journeys across SUPER_ADMIN / LAB / DOCTOR personas: signup, onboarding, MFA, screening flow, billing, error UX | **20 total: 3 blockers / 14 friction / 3 works-well** |

## Top findings across all three audits (fix first)

Ranked by a blunt product-impact lens — what would actually hurt a paying customer or operator in the first week of real use.

### Ship-blockers (fix this week)

1. **MFA onboarding is silently broken for first-login LAB users** — [user-seamlessness §LAB finding 1](user-seamlessness.md). The login response sets `mfaSetupRequired: true`, the frontend ignores it, the user lands on the onboarding wizard which silently 403s on every API call. Every brand-new lab admin hits this. Fix ≈ 1 hour.

2. **"Use a backup code instead" button has no onClick handler** — [user-seamlessness §LAB finding 2](user-seamlessness.md). Dead UI. A user who has lost their authenticator clicks it and nothing happens. Fix ≈ 2 hours.

3. **Nginx in production is loading `nginx.testing.conf`, not `nginx.prod.conf`** — [production-seamlessness D1](production-seamlessness.md). The two files have diverged. Any future edit to the "prod" file will silently have zero effect. Rename or delete one. Fix ≈ 10 minutes.

4. **Partial tenant migration + auto-rollback leaves DB inconsistent** — [production-seamlessness D3](production-seamlessness.md). If `migrate_schemas` applies migration N for tenant A but fails for tenant B, auto-rollback reverts the *image* but tenant A's DB stays migrated — now incompatible with the rolled-back code. Single biggest silent deploy risk.

5. **Redis is a single point of failure for everything** — [production-seamlessness F1](production-seamlessness.md). Cache, Celery broker, Channels, PlanLimitMiddleware, rate limiting all fail together when Redis hiccups. Graceful degradation partially exists (PlanLimitMiddleware fails open) but the full blast radius isn't documented.

### Security mediums (fix this month)

6. **DOCTOR can attribute screenings to a different doctor via client-supplied `doctorId`** — [security Finding 1](security.md). Every other DOCTOR-reachable view filters by `request.user.email`; `PredictView` is the outlier. A malicious doctor can pollute another doctor's case list and re-route high-risk alerts.

7. **DOCTOR can enumerate any patient's consent status** — [security Finding 2](security.md). `ConsentStatusView` only checks lab-association, not doctor-patient. Iterating patient IDs reveals the tenant's full active-patient directory.

8. **`FHIRBundleView` skips consent validation, DOCTOR isolation, and CBC range checks** — [security Finding 3](security.md). A FHIR ingest route that escapes all the guardrails the JSON predict path enforces.

9. **Password-setup / reset tokens survive password rotation** — [security Finding 4](security.md). A stolen provisioning email is replayable until the user's first explicit login triggers `last_login`. Race condition on initial account claim.

### Operational gaps (fix before scaling)

10. **SetPassword success screen shows the plaintext password in the DOM** — [user-seamlessness §LAB finding 3](user-seamlessness.md). Also a minor security leak. One-line frontend fix.

11. **Deploy has a ~45-60s hard cut where nginx can't reach backend** — [production-seamlessness D2](production-seamlessness.md). No blue/green, no request draining. Acceptable at current scale, but document it.

12. **No offsite backup configured** — [production-seamlessness B1-B3](production-seamlessness.md). Documented gap; local 7-day chain verified. User has no payment method for R2/B2 yet. Manual scp pull procedure in [RUNBOOK.md](../RUNBOOK.md).

13. **402 "monthly limit reached" surfaces as generic screening error, not a dashboard CTA** — [user-seamlessness cross-cutting](user-seamlessness.md). Users hit this every subsequent predict attempt until they find the upgrade flow themselves.

14. **No trial-expiry warning email** — [user-seamlessness §LAB finding 9](user-seamlessness.md). `expire_trials` task transitions TRIAL→EXPIRED silently. Users who don't log in miss the cliff.

## Explicitly accepted risks (documented, not findings)

- **Sync tenant creation** — operator waits 5-15s per click. Workaround: onboard one at a time. See RUNBOOK §9.
- **Login throttle 5/min per IP** — demos from a single wifi trip after 5 logins. Workaround: space logins or hotspot.
- **Single VPS, no HA** — hardware failure = downtime until BigRock reboots. UptimeRobot + Uptime-Kuma provide external visibility.

## What's working well

Don't miss these — each audit carved out a "works well" section because it matters for morale and regression avoidance.

- PHI encryption (MultiFernet with rotation support) and HMAC-chained audit log are solid — [security §"Already done well"](security.md)
- DOCTOR isolation on *read* paths (review, explain, trend, cases) is correctly enforced — [user-seamlessness §DOCTOR](user-seamlessness.md), [security Finding 1 context](security.md)
- Consent UX is genuinely clean; the auto-resume-screening-after-consent flow is a nice touch — [user-seamlessness §cross-cutting](user-seamlessness.md)
- Alert rules are well-scoped with runbook_url annotations; every alert maps to a playbook in RUNBOOK.md — [production-seamlessness §Observability](production-seamlessness.md)
- Restore drill is actually tested end-to-end against a real local backup — [production-seamlessness §Backup+DR](production-seamlessness.md)

## How to use these reports

- **Before a deploy:** scan the "Deploy path" section of production-seamlessness.md and the "Works well" lists for any regressions.
- **Before adding a new DOCTOR-reachable endpoint:** re-read security Findings 1-3. The pattern is consistent: always filter by `request.user.email` → `Doctor.filter(email=..., is_active=True)`.
- **Before onboarding a new customer:** walk through the user-seamlessness blockers. Fix those three and the first-day experience improves dramatically.
- **When an incident fires:** the runbook has per-alert playbooks. Production-seamlessness §Runbook notes what's missing.

## Next audit pass (when to revisit)

- **After MFA flow fixes ship:** re-run the user-seamlessness audit's first-login section to confirm routing is clean.
- **After offsite backup wires up:** re-run production-seamlessness §Backup to confirm RPO.
- **Before pen testing (Phase 4):** run a targeted security audit with a real exploitation harness, not code review.
- **After ~100 tenants:** re-audit scaling cliffs in production-seamlessness §Scaling. PgBouncer pool and uvicorn worker count may need sizing.

## Methodology notes

- All three reports were produced by independent subagents scoped to non-overlapping domains.
- The security audit deliberately skipped the recent-diff scope (another pass already covered it) and looked at the whole current codebase.
- Production seamlessness was a code-review audit — live VM verification would require additional work; items marked "not verified on live VM" in that report need real SSH time before acting on them.
- Findings are confidence-filtered: security ≥7/10, UX/ops audits prioritize impact. Lower-confidence hunches were dropped rather than reported.

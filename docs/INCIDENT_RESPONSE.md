# Incident Response Runbook — ClinomicLabs

**Status:** skeleton (P0-3 of DPDP POA).
**Owner:** `{{DPO_NAME}}` (Data Protection Officer) — see `/grievance`.
**Last tabletop drill:** pending — schedule first drill ≤ 30 days after sign-off.
**Cross-references:** [DPDP POA](../DPDP_HANDOVER.md) §P0-3, [DATA_MINIMISATION_AUDIT.md](DATA_MINIMISATION_AUDIT.md), [RUNBOOK.md](RUNBOOK.md).

---

## 0. Scope

This runbook applies to any of the following that affect ClinomicLabs production or any Lab tenant:

- Unauthorised access to, acquisition of, or disclosure of personal data (DPDP Act §8(6)).
- Compromise of integrity, availability, or confidentiality of the platform or its data.
- Compromise of a credential (API key, webhook secret, master encryption key, DB password, host SSH key).
- Anomalous ML output causing, or likely to cause, a clinical decision error under CDSCO Class A SaMD guidance.
- Compromise of a Data Processor with access to our data (Razorpay, Sentry, S3/R2, email).

**Out of scope:** routine operational outages without data implications — handle via [RUNBOOK.md](RUNBOOK.md).

---

## 1. Named roles

Fill in with real names before first drill; `{{placeholders}}` are intentional.

| Role | Responsibility | Current holder |
|---|---|---|
| **Incident Commander (IC)** | Decides severity, drives the response, owns the timeline and the post-mortem. | `{{IC_NAME}}` |
| **Communications Lead** | Single owner of all external comms (principals, labs, DPB, press). Nothing goes out without their approval. | `{{COMMS_LEAD}}` |
| **Legal Counsel** | Establishes privilege, reviews DPB/CDSCO/customer notifications before they leave. | `{{LEGAL_COUNSEL}}` |
| **Data Protection Officer** | DPDP Act §8 accountability, principal-notification owner. Cannot be Param (see POA governance). | `{{DPO_NAME}}` |
| **Security Engineer on-call** | Technical detection, triage, containment, eviction, evidence preservation. | rotation — see PagerDuty `security_incident` schedule |
| **Cyber-liability insurance contact** | Must be notified within the policy window (typically 24–48 hrs). | `{{INSURANCE_BROKER}}` — policy `{{POLICY_NO}}` |
| **CDSCO Medical Device Responsible Person** | Notifies CDSCO if the incident relates to SaMD output being relied on for clinical decisions. | Param Barodia (per MDR Rule 7(3)). |

---

## 2. Severity classification

Decide severity at the end of triage, **before** legal counsel is notified (the counsel notification itself is the act that establishes privilege over subsequent written communications — see §3 step 2).

| Level | Criteria | External notification |
|---|---|---|
| **Sev-1** | Confirmed unauthorised access to, or exfiltration of, personal data. Production MEK compromise. Widespread classifier output failure affecting multiple labs. | DPB + affected principals + affected Labs + cyber insurance + CDSCO (if SaMD-output related). |
| **Sev-2** | High-confidence signal of attempted breach with no confirmed exfiltration. Partial credential compromise (non-MEK). Classifier anomaly affecting a single tenant. | Cyber insurance within 48 h. Customer notification via Comms Lead only if required by contract. |
| **Sev-3** | Low-confidence signal, contained to test/staging, or a near-miss. | Internal log only. |

Move **up** a level when in doubt. Down-classifying after the fact is allowed; retroactively up-classifying is not and complicates notification timing.

---

## 3. Response playbook

### Step 1 — Detect
- Prometheus `security_incident` alert pages the on-call engineer.
- Sources: failed-login spikes, unusual audit-log patterns (see `apps.core.audit.log_phi_access`), Sentry alerts tagged `security`, tenant escalations.
- Acknowledge the page. Start an incident channel named `#inc-YYYY-MM-DD-<short-tag>`.

### Step 2 — Triage and classify
- IC is the first engineer on the page unless they hand off explicitly.
- Produce a two-sentence scope statement: *what* may have happened, *which* data is potentially in scope.
- Set Sev level per §2.
- **Notify Legal Counsel** before any written technical analysis is circulated. From this moment forward, mark all investigation documents “Privileged & Confidential — Prepared at the direction of counsel.”
- Notify DPO (who owns principal notification).

### Step 3 — Contain
- Revoke compromised credentials immediately. Specific playbooks:
  - API key → `apps.billing.models.APIKey.is_active=False` via admin, log reason.
  - Webhook secret → rotate via `/api/billing/webhooks/{id}/rotate` (re-issues secret; receiver must re-fetch).
  - MFA compromise of a single user → `apps/core/mfa.MFAManager.disable_mfa` + force password reset.
  - MEK compromise → initiate key rotation per `apps/core/crypto.py` docstring; all ciphertext must be re-encrypted under the new primary key before old keys are removed.
  - DB password → rotate via infra, restart services.
- Isolate affected nodes if host-level compromise. Snapshot volumes for forensics **before** re-imaging.
- Block the offending IPs at nginx if origin is identifiable.

### Step 4 — Notify
Ordering matters. Do not skip ahead.

1. Legal Counsel (already done in step 2).
2. Cyber-liability insurance broker. **Missing this notification voids coverage.** Template: `docs/templates/INSURANCE_NOTIFICATION.md`.
3. **Data Protection Board of India** — within 72 hours of becoming aware (DPDP Act §8(6)). Template: `docs/templates/DPB_NOTIFICATION.md`. Draft goes through Legal + Comms Lead before sending.
4. **Affected data principals** — in the manner prescribed by DPDP Rules (as of this writing: by the mode of communication already on file). Template: `docs/templates/PRINCIPAL_NOTIFICATION.md`.
5. **Affected Labs** — contractual Data Processor notification under the Laboratory Services Agreement §8 and any executed DPA. Template: `docs/templates/LAB_NOTIFICATION.md`.
6. **CDSCO** — if the incident affects the software’s output being relied on for clinical decisions, notify the CDSCO officer of record per MDR 2017 adverse-event reporting. Template: `docs/templates/CDSCO_NOTIFICATION.md`.

No public statement without Comms Lead + Legal Counsel both approving.

### Step 5 — Preserve evidence
- Freeze relevant log streams (`audit_log_entries`, nginx access logs, Sentry events). Export a time-boxed snapshot to an evidence-only S3 bucket with object-lock.
- Hash each artefact (SHA-256) and record the hash in the incident document. The hash chain of `AuditLogEntry` is itself tamper-evident — preserve the last sequence number and entry_hash at the time of detection as a verifiable anchor.

### Step 6 — Evict and remediate
- Patch or rotate whatever was exploited.
- Re-enable systems only when:
  - the vulnerability is patched,
  - affected credentials are fully rotated,
  - monitoring is tuned to detect a recurrence,
  - Legal has confirmed there is no reason to keep the system off.

### Step 7 — Post-mortem
- Within 5 business days of Sev-1/Sev-2 resolution, produce a blameless post-mortem stored in `docs/INCIDENTS/YYYY-MM-DD-<short-tag>.md`.
- Must include: timeline, root cause, user-visible impact, principals affected, notifications sent (with timestamps), corrective action with owners and due dates.
- Share with the Board at the next regular meeting. Provide a redacted summary to the DPO register.

---

## 4. Monitoring hookup (Prometheus)

`monitoring/alert-rules.yml` must include a `security_incident` alert family that pages the on-call when any of the following fire:

- `rate(failed_logins_total[5m]) > THRESHOLD`
- Burst of `4xx` on `/api/auth/*` above baseline.
- Any write to `AuditLogEntry` with `action` containing `ADMIN_OVERRIDE` or `MFA_DISABLED` outside business hours.
- Sentry event tagged `security`.
- Webhook-signing HMAC-verification failure above baseline.
- `health/ready` failures attributable to credential or encryption-subsystem errors.

Wire by running the first tabletop drill — see §5.

---

## 5. Tabletop drill template

Run a tabletop every quarter, and once immediately after sign-off of this runbook. Record in `docs/INCIDENTS/DRILL-YYYY-MM-DD.md`.

- Scenario: IC picks one from a rotating list — credential leak on GitHub, Sev-1 MEK compromise, ML output regression affecting a tenant, Data Processor breach (Razorpay).
- Duration: 60 minutes.
- Everyone named in §1 attends. No tech actions taken — the drill exercises the decision path and the comms path.
- At end, fill in `docs/INCIDENTS/DRILL-YYYY-MM-DD.md`:
  - Time to severity decision.
  - Who was notified, in what order, with what artefact.
  - Any role that could not be covered because the named holder was unavailable — fix by identifying a deputy before the next drill.

---

## 6. Notification templates

Skeletons stored separately so Comms Lead can customise per incident without editing this runbook:

- `docs/templates/DPB_NOTIFICATION.md`
- `docs/templates/PRINCIPAL_NOTIFICATION.md`
- `docs/templates/LAB_NOTIFICATION.md`
- `docs/templates/INSURANCE_NOTIFICATION.md`
- `docs/templates/CDSCO_NOTIFICATION.md`

All templates are placeholder-heavy and must be reviewed by Legal before first live use.

---

## 7. Known gaps

These are intentionally deferred to the DPDP POA phases that own them:

- Legal Counsel engagement — gated on counsel retainer (POA Governance §).
- Insurance broker details — gated on cyber-liability policy binding.
- DPO appointment — gated on Board resolution naming the DPO (POA governance §).
- CDSCO Responsible Person runbook — the incident path is in place; the CDSCO reclassification risk (see Legal Framework §6.2) is not re-visited here.

When each gap is closed, fill in the placeholders and mark the row in §1 / §4 active.

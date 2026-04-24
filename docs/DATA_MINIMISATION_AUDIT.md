# Data Minimisation Audit — v1

**Status:** signed off 2026-04-24 (engineering)
**Covers:** P1-17 of the DPDP POA
**Source code scope:** `backend_v3/apps/screening/`, `backend_v3/apps/core/`, `backend_v3/apps/billing/`, `backend_v3/apps/analytics/`

DPDP Act §4(1)(b) requires that personal data be collected and processed only to the extent necessary for the specified purpose. This document enumerates every PHI-adjacent field the platform ingests or persists, justifies its retention, and records the evidence that non-essential fields are stripped at the ingestion boundary.

---

## 1. Ingestion paths

There are **three** paths by which patient data can enter the platform:

| # | Path | Who triggers | Raw format |
|---|---|---|---|
| A | Interactive single-screening | Lab user via UI | JSON POST to `/api/screening/classify` |
| B | CSV bulk import | Lab user via UI | multipart file upload |
| C | FHIR adapter | Programmatic integration | JSON POST to `/api/screening/fhir/predict` |

No PDF/OCR parser exists in the codebase. Prior POA wording referencing `apps/ingestion/parsers.py` describes a hypothetical future path and is carried forward as a guard rail for when PDF ingestion is added.

---

## 2. Field inventory

### 2.1 Patient-identifying fields

| Field | Source | Storage | Justification | Minimisation action |
|---|---|---|---|---|
| `patient_id` | lab-supplied external reference | plaintext TEXT on `Patient` | Required to correlate a screening with subsequent clinical action at the lab. No free-name identifier. | Not a name; retained as-is. |
| `patient_name` | CSV (optional) or UI form | Fernet-encrypted on `Patient.name_encrypted` | Required for lab-internal record linkage and reports. | Never stored plaintext; accessed via `Patient.name` property. |
| `age` | CSV / UI / FHIR | Fernet-encrypted on `Patient.age_encrypted` AND (via CBC snapshot) encrypted on `Screening.cbc_snapshot_enc` | Required input to the classifier and to the narrative engine. | No raw plaintext in DB. A coarse `Screening.age_bucket` (pediatric / young_adult / middle_aged / elderly) is stored for analytics filters; this is a low-sensitivity derivation, not raw age. |
| `sex` | CSV / UI / FHIR | Fernet-encrypted on `Patient.sex_encrypted` AND (via CBC snapshot) encrypted on `Screening.cbc_snapshot_enc` | Required input to the classifier; sex-adjusted thresholds are clinically different. | No raw plaintext; normalised `Screening.sex_code` (M/F/empty) stored for analytics filters. |
| `email`, `phone`, `address`, `date_of_birth` | — | **Not accepted by any intake endpoint.** | — | The CSV parser uses a targeted `DictReader` with a fixed whitelist of keys (`_CSV_TO_CBC`, plus `patient_id`, `patient_name`, `age`, `sex`, `lab_id`, `doctor_id`); any additional CSV columns are silently ignored. The UI form does not expose these fields. |
| `referring_doctor_code` | CSV / UI / FHIR | plaintext TEXT on `Doctor` | Operational — doctor registration identifier, not patient PHI. | Not PHI; retained. |

### 2.2 CBC and clinical fields

All CBC parameters (`Hb`, `RBC`, `HCT`, `MCV`, `MCH`, `MCHC`, `RDW`, `WBC`, `Platelets`, `Neutrophils_%`, `Lymphocytes_%`, `Monocytes_%`, `Eosinophils_%`, `Basophils_%`) are:

- Required inputs to the classifier (see [Intended Purpose Statement](legal/CLINOMICLABS_LEGAL_FRAMEWORK.md#21-intended-purpose)).
- Fernet-encrypted at rest inside `Screening.cbc_snapshot_enc` — new writes go through `Screening.save()` which transparently moves `cbc_snapshot=` assignments into the encrypted column.  The schema change lands in migration `screening/0012_encrypt_cbc_snapshot.py`; legacy plaintext rows are backfilled via the one-shot `python manage.py encrypt_plaintext_columns --cbc-snapshots` run at a chosen maintenance window (not executed at container start to avoid blocking deploys).
- Never persisted outside of encrypted columns on a `Screening` row or its `Consent`/`Patient` relations.

### 2.3 Secrets and third-party credentials

| Field | Storage | Since |
|---|---|---|
| `WebhookEndpoint.secret` | Fernet-encrypted (`EncryptedTextField`) | migration `billing/0008_encrypt_webhook_secret.py` (schema); backfill via `manage.py encrypt_plaintext_columns --webhook-secrets` |
| `MFASettings.secret_key` | Fernet-encrypted text (see `apps/core/mfa.py`) | pre-existing |
| `Patient.name_encrypted`, `age_encrypted`, `sex_encrypted` | Fernet-encrypted text | pre-existing |
| `APIKey.key_hash` | SHA-256 digest only; raw key shown once | pre-existing |
| `RefreshToken.token_hash` | SHA-256 digest only | pre-existing |
| `MFASettings.backup_codes` | SHA-256 hashes | pre-existing |

---

## 3. CSV bulk import — defence-in-depth audit

File: `backend_v3/apps/screening/tasks.py::process_bulk_import`.

**Accepted columns (whitelist):**
```
patient_id, patient_name, lab_id, doctor_id,
age, sex,
hb, rbc, hct, mcv, mch, mchc, rdw, wbc, plt, neu_pct, lym_pct
```

**Non-PHI columns silently dropped:** all columns outside this whitelist. Python's `csv.DictReader` is used with a fixed `_CSV_TO_CBC` mapping plus an explicit `_REQUIRED_COLS` set; anything not matched is never accessed and therefore never persisted.

**Error-path PHI hardening:** error messages stored on `BulkImportJob.error_detail` are truncated to 200 chars to bound the risk of future exception strings that might include row content leaking into the job status JSON. See `process_bulk_import` exception handler.

**Unit test evidence:** `tests/test_bulk_import.py` (pre-existing) exercises the parser with minimal fixtures. The `tests/test_audit_sanitise.py` suite added as part of P1-10 covers the audit-log path that a bulk-import run traverses.

---

## 4. Audit log hygiene (P1-10 cross-reference)

Every `log_phi_access(request, patient_id, action, details)` call now routes `details` through `apps.core.audit.sanitise_details()`, which:

1. Drops keys whose name (case-insensitive substring match) is in a PHI block-list: `name`, `email`, `phone`, `mobile`, `address`, `dob`, `date_of_birth`, `age`, `sex`, `gender`, `hb`, `hgb`, `rbc`, `hct`, `mcv`, `mch`, `mchc`, `rdw`, `wbc`, `neutrophil`, `lymphocyte`, `monocyte`, `eosinophil`, `basophil`, `platelet`, `cbc_snapshot`, `cbc`, `b12`, `ferritin`, `clinical_note`, `narrative`, `note`.
2. Hashes any free-text string longer than 128 chars with SHA-256, preserving a hash prefix and a length tag so long payloads are traceable without content retention.
3. Walks nested dicts and lists recursively.

See `tests/test_audit_sanitise.py` (17 cases, all pass).

---

## 5. Retention (forward-link to P1-9)

This audit only covers ingestion-time minimisation. The retention periods for each data class (patient-identifiable, device performance logs, audit logs, contracts) are scoped to P1-9 / `DATA_RETENTION_POLICY.md` and do not bind this document.

---

## 6. Open items

- If/when a PDF OCR parser is introduced (`apps/ingestion/parsers.py` or equivalent), re-run this audit with the same whitelist approach. Parse targeted fields only; strip everything else at the parser boundary.
- Training data provenance for the CatBoost classifier is documented separately under P1-18 `TRAINING_DATA_PROVENANCE.md`.
- Review this document annually and on any new ingestion pathway.

---

*Signed off by engineering.  Not a substitute for the counsel review called out as governance in the DPDP POA.*

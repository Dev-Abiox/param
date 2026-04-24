# CDSCO — Adverse Event / Field Safety Notice

Use only when the incident affects the Clinomic SaMD's output such that a clinical decision may have been or could be influenced. Filed by the Designated Medical Device Responsible Person (Param Barodia per MDR Rule 7(3)), under MDR 2017 post-market surveillance and CDSCO Oct 2025 SaMD draft guidance.

---

To: `{{CDSCO_OFFICER_OF_RECORD}}`, Central Drugs Standard Control Organization
Cc: `{{STATE_LICENSING_AUTHORITY}}`
From: Param Barodia, Designated Medical Device Responsible Person, Arogya BioX Private Limited
Date: `{{SENT_AT}}`

Subject: Field safety notice / adverse event — Clinomic B12 Screening Software — incident INC-`{{YYYY-MM-DD-SHORT-TAG}}`

---

1. **Manufacturer:** Arogya BioX Private Limited.
2. **Device:** Clinomic B12 Screening Software — SaMD, Class A (per authoritative Intended Purpose — see Legal Framework §2.1).
3. **Manufacturing licence / registration reference:** `{{LICENCE_REF}}`.
4. **Device version / model artifact hash:** `{{MODEL_VERSION}}` / `{{MODEL_ARTIFACT_HASH}}`.
5. **Event type:**
   - `{{software-output-regression | data-integrity | availability | other}}`.
6. **Event summary (factual only):** `{{2 sentences}}`.
7. **Patient impact assessment:**
   - Number of screenings potentially affected: `{{N}}`.
   - Nature of potential impact on clinical decision: `{{describe the pathway — e.g. workflow recommendation mislabelled, upstream CBC data corruption, etc.}}`.
   - Actions labs should take: `{{LIST}}`.
8. **Corrective action taken / planned:**
   - Immediate: `{{containment — e.g. model served from previous stable artifact hash}}`.
   - Near-term: `{{patch, retrain, re-issue advisory}}`.
9. **Advisory to end-users:** attached at `docs/templates/FIELD_SAFETY_NOTICE_USERS.md` (draft — needs Legal approval before release).
10. **Contact for CDSCO enquiries:**
    Param Barodia — `{{PARAM_EMAIL}}` — `{{PARAM_PHONE}}`.

Attachments:
- Incident timeline extract (factual only — privileged investigation material withheld pending counsel review).
- Model performance diff: before/after affected deployment window.
- Copy of DPB notification (where the event has a data-protection dimension).

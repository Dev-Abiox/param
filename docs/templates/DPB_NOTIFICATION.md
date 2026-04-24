# Data Protection Board of India — Personal Data Breach Notification

**Regulatory basis:** DPDP Act 2023 §8(6) read with the Digital Personal Data Protection Rules (when notified).
**Deadline:** within 72 hours of becoming aware of the breach.
**Prepared by:** `{{DPO_NAME}}`, Data Protection Officer, Arogya BioX Private Limited.
**Reviewed by:** Legal Counsel `{{LEGAL_COUNSEL}}`, Communications Lead `{{COMMS_LEAD}}`.
**Incident reference:** INC-`{{YYYY-MM-DD-SHORT-TAG}}`.

---

## 1. Fiduciary identification

- **Legal name:** Arogya BioX Private Limited (“ClinomicLabs”).
- **Registered address:** `{{ADDRESS}}`.
- **CIN:** `{{CIN}}`.
- **DPO / Grievance Officer:** `{{DPO_NAME}}`, `{{DPO_EMAIL}}`, `{{DPO_PHONE}}`.

## 2. Incident summary

- **Nature of personal data affected:** `{{CATEGORIES — e.g. patient name, age, sex, CBC values, contact details}}`.
- **Categories of data principals affected:** patients of `{{LAB_NAMES}}`.
- **Approximate number of principals affected:** `{{N}}`.
- **Approximate number of records affected:** `{{M}}`.
- **Date/time of discovery (IST):** `{{DISCOVERED_AT}}`.
- **Date/time of occurrence (IST), if known:** `{{OCCURRED_AT}}`.
- **Location of processing at time of incident:** `{{CITY, STATE, COUNTRY — typically Mumbai, India (production DB)}}`.
- **Mode of unauthorised access/loss:** `{{BRIEF DESCRIPTION}}`.

## 3. Likely consequences

State the worst-case consequences realistically, in plain language. Examples:
- Potential unauthorised access to patient identifiers linked to laboratory results.
- Potential re-identification of data principals if the breach included both identifiers and health data.
- No reason to believe financial credentials were exposed.

## 4. Measures taken and proposed

- **Containment actions already taken:** `{{LIST — credential rotation, node isolation, etc.}}`.
- **Remediation underway:** `{{LIST}}`.
- **Mitigation offered to principals:** `{{e.g. updated password guidance, free credit-monitoring window if applicable, point of contact for questions}}`.

## 5. Notifications to principals

- **Mode of notification:** `{{email / SMS / portal message}}`.
- **Date of intended notification:** `{{DATE}}`.
- **Sample of the notification text:** see `docs/templates/PRINCIPAL_NOTIFICATION.md` with this incident's placeholders filled in.

## 6. Contact for further information

`{{DPO_NAME}}` — `{{DPO_EMAIL}}` — `{{DPO_PHONE}}`.

---

*This notification is prepared under statutory compulsion. It does not constitute an admission of liability. Filed under privilege where applicable.*

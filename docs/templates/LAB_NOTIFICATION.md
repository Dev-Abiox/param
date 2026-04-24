# Lab Tenant Breach Notification — Processor → Fiduciary

Notification from ClinomicLabs to an affected Lab customer under the Laboratory Services Agreement §8 and any executed Data Processing Agreement. Sent by the Communications Lead with Legal approval.

---

Subject: Security-incident notification — Arogya BioX (Clinomic) — incident INC-`{{YYYY-MM-DD-SHORT-TAG}}`

To: `{{LAB_POC_NAME}}`, `{{LAB_NAME}}`
From: `{{DPO_NAME}}`, Data Protection Officer, Arogya BioX Private Limited
Date: `{{SENT_AT}}`

---

1. **Incident reference:** INC-`{{YYYY-MM-DD-SHORT-TAG}}`.

2. **Summary.** `{{2 sentences describing the incident in operational terms.}}`

3. **Your tenant specifically.**
   - Tenant ID: `{{TENANT_ID}}`.
   - Data categories potentially affected: `{{LIST}}`.
   - Estimated patient record count affected within your tenant: `{{N}}`.
   - Evidence basis for the estimate: `{{e.g. audit-log review time-boxed to X–Y IST}}`.

4. **Actions we have taken.**
   - Contained at `{{CONTAINED_AT}}`.
   - Notified the Data Protection Board of India within the statutory 72-hour window (filed `{{FILED_AT}}`).
   - Rotated affected credentials / isolated affected systems as described in the attached timeline.

5. **Your role as Data Fiduciary (if DPA Option A applies).**
   Under §8(6) of the DPDP Act, you as the Data Fiduciary for your patients are responsible for principal notification where required. We are providing the information in §3 to support you in meeting that obligation. We have prepared a sample notification template for you at `docs/templates/PRINCIPAL_NOTIFICATION.md`; please adapt to your brand and legal voice.

6. **Joint Fiduciary mode (if DPA Option B applies).**
   Under our Joint Fiduciary arrangement, we are notifying affected principals directly on `{{DATE}}` via `{{MODE}}`. Copy of the principal notification is attached.

7. **Contact for this incident.**
   `{{DPO_NAME}}` — `{{DPO_EMAIL}}` — `{{DPO_PHONE}}`. Please route all further enquiries through this single point.

8. **Privilege.**
   This notification is shared in confidence. Factual content may be used for your own DPDP compliance and principal notifications; investigative analysis referenced herein is privileged and should not be further disclosed without prior written agreement.

Yours sincerely,

`{{DPO_NAME}}`
Data Protection Officer, ClinomicLabs

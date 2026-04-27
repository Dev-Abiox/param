/**
 * Shared PDF report generation for Clinomic B12 screening results.
 *
 * Used by:
 *   - ResultPanel  (live screening result after a new prediction)
 *   - PatientRecords  (re-generate from stored cbc_snapshot via Download button)
 */

import { jsPDF } from "jspdf";
import autoTable from "jspdf-autotable";
import { INITIAL_CBC_ROWS } from "@/constants";
import {
  PATIENT_EMPTY_STATE_TEXT,
  PATIENT_MACROCYTIC_FOOTNOTE,
  buildResultFromScreening as _buildResultFromScreening,
  formatReasoning as _formatReasoning,
  moduleCells as _moduleCells,
  patientModuleCard,
  tbd,
} from "./clinicalRulesHelpers";

// Re-export the pure helpers so existing import sites keep working
// after the helpers were moved to clinicalRulesHelpers.js.
export const buildResultFromScreening = _buildResultFromScreening;
export const formatReasoning = _formatReasoning;
export const moduleCells = _moduleCells;

// Map cbc_snapshot field names to INITIAL_CBC_ROWS keys.
// Short keys (Hb, RBC, …) are the actual format stored by the DRF serializer;
// long keys (Hb_g_dL, …) are kept for backward-compat with any legacy snapshots.
const SNAPSHOT_KEY_MAP = {
  // Short keys — actual stored format
  Hb:            "hb",
  RBC:           "rbc",
  WBC:           "wbc",
  Platelets:     "plt",
  HCT:           "hct",
  MCV:           "mcv",
  MCH:           "mch",
  MCHC:          "mchc",
  RDW:           "rdw",
  Neutrophils:   "neu_pct",
  Lymphocytes:   "lym_pct",
  // Long keys — backward compatibility
  Hb_g_dL:            "hb",
  RBC_million_uL:      "rbc",
  WBC_10_3_uL:         "wbc",
  Platelets_10_3_uL:   "plt",
  HCT_percent:         "hct",
  MCV_fL:              "mcv",
  MCH_pg:              "mch",
  MCHC_g_dL:           "mchc",
  RDW_percent:         "rdw",
  Neutrophils_percent: "neu_pct",
  Lymphocytes_percent: "lym_pct",
};

/**
 * Build the cbcRows array expected by generateReport() from a stored cbc_snapshot.
 *
 * @param {object} cbcSnapshot  - The cbc_snapshot JSON from the Screening model.
 * @returns {Array}             - Row objects matching the INITIAL_CBC_ROWS shape.
 */
export function buildCbcRowsFromSnapshot(cbcSnapshot) {
  return INITIAL_CBC_ROWS.map((row) => {
    // Find the snapshot key that maps to this row's key
    const snapshotKey = Object.keys(SNAPSHOT_KEY_MAP).find(
      (k) => SNAPSHOT_KEY_MAP[k] === row.key
    );
    const value = snapshotKey !== undefined ? cbcSnapshot[snapshotKey] : "";
    return { ...row, value: value !== undefined ? String(value) : "" };
  });
}

// buildResultFromScreening lives in ./clinicalRulesHelpers.js and is
// re-exported above for backward-compat with existing import sites.

const loadImage = (url) =>
  new Promise((resolve, reject) => {
    const img = new Image();
    img.src = url;
    img.onload = () => resolve(img);
    img.onerror = reject;
  });

// Clinical-rule presentation helpers are defined in
// ./clinicalRulesHelpers.js and re-exported above.  Inside the PDF
// generator we just use the local aliases.

/**
 * Generate a jsPDF document for a B12 screening report.
 *
 * Two templates live behind one function:
 *
 *   - **legacy**     — the pre-disclosure-spec layout that production
 *                       has been serving since launch.  No manufacturer
 *                       header, no pathologist sign-off block, minimal
 *                       footer.  The Workflow Recommendations section
 *                       is suppressed (Option A).
 *   - **spec_v1**    — the Patient PDF Disclosure Specification (April
 *                       2026) layout: Block A header (manufacturer ID +
 *                       beta-phase line), CBC + indices, Block C / D
 *                       Workflow Recommendations with patient-facing
 *                       translations + empty-state card + macrocytic
 *                       footnote, Block E pathologist sign-off, Block
 *                       F mandatory footer.  Renders ``[TBD]`` for any
 *                       per-lab placeholder that has not yet been
 *                       configured.
 *
 * Switch is keyed on ``result.labWorkflowRecsEnabled`` (sourced from
 * ``Lab.patient_pdf_workflow_recs_enabled`` per the readiness audit).
 * Default False fails closed to legacy.  No lab is enabled in
 * production until counsel sign-off + DPO appointment + signature
 * workflow audit are all complete; flipping the flag is a manual
 * operations step, not exposed in any admin UI yet.
 *
 * Preview mode (``options.previewMode === true``)
 *   - Forces the spec_v1 template regardless of the per-lab flag.
 *   - Applies a diagonal "PREVIEW — NOT FOR PATIENT DISTRIBUTION"
 *     watermark on every page.
 *   - Intended for SUPER_ADMIN review of the disclosure language
 *     before counsel sign-off.  The watermark is non-removable from
 *     the rendered PDF (drawn on top of all content) so a previewed
 *     PDF cannot accidentally be forwarded to a patient as a real
 *     report.
 *   - Does NOT touch the ``labWorkflowRecsEnabled`` field on the
 *     result object — it's a render-time-only override scoped to the
 *     single PDF.
 *
 * @param {object} patient  - { name, id, age, sex, date, labId }
 * @param {object} result   - { probabilities, interpretation, recommendation, indices, ... }
 * @param {Array}  cbcRows  - INITIAL_CBC_ROWS-shaped array with .value populated
 * @param {object} [options]
 * @param {boolean} [options.previewMode=false] — see above.
 * @returns {Promise<jsPDF>}
 */
export async function generateReport(patient, result, cbcRows, options = {}) {
  const preview = options.previewMode === true;
  let doc;
  if (preview || result?.labWorkflowRecsEnabled === true) {
    // Preview mode renders spec_v1 regardless of the per-lab flag, so
    // SUPER_ADMINS can spot-check the disclosure language without
    // flipping any live lab.
    const overridden = preview ? { ...result, labWorkflowRecsEnabled: true } : result;
    doc = await _generateReportSpecV1(patient, overridden, cbcRows);
  } else {
    doc = await _generateReportLegacy(patient, result, cbcRows);
  }
  if (preview) {
    _applyPreviewWatermark(doc);
  }
  return doc;
}

/** Stamp every page with a diagonal "PREVIEW — NOT FOR PATIENT
 * DISTRIBUTION" watermark.  Drawn last so it overlays all rendered
 * content; a viewer cannot strip the watermark by scrolling under it.
 *
 * The watermark is ALSO applied to the legacy template when called
 * (currently it never is — preview mode forces spec_v1 — but if a
 * future caller wants a watermarked legacy preview, the function is
 * shape-agnostic). */
function _applyPreviewWatermark(doc) {
  const pageCount = doc.internal.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    doc.saveGraphicsState();
    if (typeof doc.GState === "function") {
      // jsPDF >= 2.x: use a graphics state to set partial opacity
      // so the watermark doesn't bury the report content.
      doc.setGState(new doc.GState({ opacity: 0.18 }));
    }
    doc.setFont("helvetica", "bold");
    doc.setFontSize(48);
    doc.setTextColor(220, 38, 38);  // red-600
    // Diagonal across the page — A4 is 210x297mm, centre is (105,148.5).
    // Rotate 45° about the centre.
    doc.text("PREVIEW — NOT FOR PATIENT DISTRIBUTION", 105, 150, {
      align: "center",
      angle: 45,
    });
    doc.restoreGraphicsState();
    doc.setTextColor(0, 0, 0);
  }
}

/**
 * Legacy template — preserved bit-for-bit from the pre-disclosure-spec
 * production behaviour.  The Workflow Recommendations section is gated
 * inside this function on ``labWorkflowRecsEnabled`` too, but that
 * branch never fires here (the outer router sends spec_v1 cases to
 * ``_generateReportSpecV1``).  The gate is kept as defence in depth so
 * a future refactor that bypasses the router still cannot leak the
 * un-translated Workflow Recommendations table to a patient PDF.
 */
async function _generateReportLegacy(patient, result, cbcRows) {
  const doc = new jsPDF();

  // ── Header ──────────────────────────────────────────────────────────────────
  doc.setFillColor(13, 148, 136);
  doc.rect(0, 0, 210, 20, "F");

  try {
    const logo = await loadImage("/clean-logo.png?v=1");
    doc.addImage(logo, "PNG", 10, 2, 16, 16);
    doc.setDrawColor(255, 255, 255);
    doc.setLineWidth(0.5);
    doc.line(28, 5, 28, 15);
    doc.setTextColor(255, 255, 255);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(18);
    doc.text("Clinomic Labs", 32, 13);
  } catch {
    doc.setTextColor(255, 255, 255);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(18);
    doc.text("Clinomic Labs", 14, 13);
  }

  doc.setFontSize(10);
  doc.setFont("helvetica", "normal");
  doc.text("Vitamin B12 Screening Report", 195, 13, { align: "right" });

  // ── Patient info ─────────────────────────────────────────────────────────
  doc.setTextColor(0, 0, 0);
  doc.setFontSize(11);

  doc.setFont("helvetica", "bold"); doc.text("Patient Name:", 14, 30);
  doc.setFont("helvetica", "normal");
  // Wrap long patient names (max 90mm before hitting the Date column)
  const nameLines = doc.splitTextToSize(patient.name || "N/A", 90);
  doc.text(nameLines, 42, 30);

  doc.setFont("helvetica", "bold"); doc.text("Patient ID:", 14, 36);
  doc.setFont("helvetica", "normal"); doc.text(patient.id || "N/A", 36, 36);

  doc.setFont("helvetica", "bold"); doc.text("Age/Sex:", 14, 42);
  doc.setFont("helvetica", "normal"); doc.text(`${patient.age || "-"} / ${patient.sex || "-"}`, 34, 42);

  doc.setFont("helvetica", "bold"); doc.text("Date:", 140, 30);
  doc.setFont("helvetica", "normal"); doc.text(patient.date || "N/A", 152, 30);

  doc.setFont("helvetica", "bold"); doc.text("Lab Name:", 140, 36);
  doc.setFont("helvetica", "normal");
  // Dynamically wrap long lab names (34mm available: 196 right margin - 162 start)
  const labName = patient.labId || "N/A";
  const labLines = doc.splitTextToSize(labName, 34);
  if (labLines.length > 1) {
    doc.setFontSize(9); // Slightly smaller for multi-line lab names
  }
  doc.text(labLines, 162, 36);
  doc.setFontSize(11); // Reset font size

  doc.setDrawColor(200, 200, 200);
  doc.setLineWidth(0.1);
  doc.line(14, 48, 196, 48);

  // ── Result ───────────────────────────────────────────────────────────────
  // Use the backend's authoritative risk classification (considers both model probability and clinical indices)
  const labelMap = { 1: "Normal", 2: "Borderline", 3: "Deficient" };
  const colorMap = { 1: [34, 197, 94], 2: [245, 158, 11], 3: [239, 68, 68] };
  const labelText = labelMap[result.label] || "Normal";
  const color = colorMap[result.label] || [34, 197, 94];

  doc.setFontSize(14);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(0, 0, 0);
  doc.text("Screening Result:", 14, 58);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(...color);
  doc.text(labelText, 55, 58);

  // ── Interpretation box ────────────────────────────────────────────────────
  doc.setFillColor(248, 250, 252);
  doc.setDrawColor(226, 232, 240);
  doc.rect(14, 68, 182, 42, "FD");

  doc.setTextColor(0, 0, 0);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.text("Clinical Interpretation:", 18, 74);
  doc.setFont("helvetica", "normal");
  doc.text(result.interpretation || "", 18, 80, { maxWidth: 174 });
  doc.setFont("helvetica", "bold");
  doc.text("Recommendation:", 18, 96);
  doc.setFont("helvetica", "normal");
  doc.text(result.recommendation || "", 18, 102, { maxWidth: 174 });

  // ── Indices table ─────────────────────────────────────────────────────────
  // Mentzer and Green-King are IDA-vs-BTT discrimination indices defined
  // for microcytic patients only.  In non-microcytic patients (MCV>=80)
  // they are mathematically computable but clinically meaningless, so
  // gate the significance text on MCV to avoid the "high Mentzer ratio
  // on a non-anemic patient is flagged Possible Iron Deficiency" trap.
  const mcvRow = (cbcRows || []).find((r) => r.key === "mcv");
  const mcvValue = parseFloat(mcvRow?.value);
  const isMicrocytic = Number.isFinite(mcvValue) && mcvValue < 80;

  const mentzerSig = isMicrocytic
    ? (result.indices.mentzer > 13 ? "Microcytic + Mentzer > 13: favors IDA over BTT" : "Microcytic + Mentzer < 13: favors BTT")
    : "Discrimination index — only meaningful in microcytic patients";
  const greenKingSig = isMicrocytic
    ? (result.indices.greenKing > 65 ? "Microcytic + G&K > 65: favors IDA over BTT" : "Microcytic + G&K < 65: favors BTT")
    : "Discrimination index — only meaningful in microcytic patients";

  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.text("Hematological Indices", 14, 120);

  autoTable(doc, {
    startY: 124,
    head: [["Index", "Value", "Clinical Significance"]],
    body: [
      ["Mentzer Index",               String(result.indices.mentzer),   mentzerSig],
      ["Green & King Index",          String(result.indices.greenKing), greenKingSig],
      ["NLR (Neutrophil/Lymphocyte)", String(result.indices.nlr),       "Inflammatory marker"],
    ],
    theme: "grid",
    headStyles: { fillColor: [13, 148, 136], fontSize: 9, fontStyle: "bold" },
    styles: { fontSize: 8, cellPadding: 3 },
    columnStyles: { 0: { fontStyle: "bold", cellWidth: 70 }, 1: { cellWidth: 30 } },
  });

  // ── Workflow Recommendations (Patient PDF Disclosure Spec — Option A) ────
  //
  // The patient receives this PDF directly (see Report Disclosure Spec,
  // §0).  The current rule output uses clinical jargon, raw confidence
  // tiers ("high"/"medium"/"low"), and module names that name conditions
  // directly — none of which is appropriate for a layperson reader and
  // none of which has counsel sign-off.
  //
  // Until counsel reviews the disclosure language and the per-lab
  // signature workflow + DPO email + grievance email are configured,
  // every patient PDF withholds the Workflow Recommendations section
  // entirely.  The on-screen ResultPanel cards (clinician-facing) are
  // unaffected — that surface is still appropriate jargon-wise for the
  // pathologist reviewing the case.
  //
  // Gate: ``result.labWorkflowRecsEnabled`` (sourced from
  // ``Lab.patient_pdf_workflow_recs_enabled``, default False).  A
  // missing / undefined flag fails closed — section is suppressed.
  // Flipping the flag to True is reserved for Option B once §5 of the
  // spec is implemented and counsel has signed off.
  if (result.labWorkflowRecsEnabled === true && result.clinicalRules) {
    const flaggedRows = ["iron_deficiency", "thalassemia_trait", "macrocytic_anemia", "anemia_subtype"]
      .map((k) => moduleCells(k, result.clinicalRules[k]))
      .filter(Boolean);

    if (flaggedRows.length > 0) {
      const rulesY = doc.lastAutoTable.finalY + 8;
      doc.setFont("helvetica", "bold");
      doc.setFontSize(11);
      doc.text("Workflow Recommendations", 14, rulesY);
      doc.setFont("helvetica", "italic");
      doc.setFontSize(8);
      doc.setTextColor(100);
      doc.text(
        "Rule-based flags from published hematology indices. Advisory; do not replace clinical judgement.",
        14, rulesY + 4, { maxWidth: 182 },
      );
      doc.setTextColor(0, 0, 0);

      autoTable(doc, {
        startY: rulesY + 8,
        head: [["Workflow", "Confidence", "Reasoning", "Recommendation"]],
        body: flaggedRows,
        theme: "grid",
        headStyles: { fillColor: [13, 148, 136], fontSize: 9, fontStyle: "bold" },
        styles: { fontSize: 8, cellPadding: 3, valign: "top" },
        columnStyles: {
          0: { fontStyle: "bold", cellWidth: 42 },
          1: { cellWidth: 22, halign: "center" },
          2: { cellWidth: 60 },
        },
      });
    }
  }

  // ── CBC table ─────────────────────────────────────────────────────────────
  const finalY = doc.lastAutoTable.finalY + 12;
  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.text("Complete Blood Count (CBC) Data", 14, finalY);

  autoTable(doc, {
    startY: finalY + 4,
    head: [["Test", "Result", "Unit", "Ref. Range"]],
    body: cbcRows.map((row) => [
      row.test,
      row.value || "-",
      row.unit,
      `${(patient.sex === "M" ? row.refRangeM : row.refRangeF).join(" - ")}`,
    ]),
    theme: "striped",
    headStyles: { fillColor: [51, 65, 85], fontSize: 9, fontStyle: "bold" },
    styles: { fontSize: 8, cellPadding: 2 },
    alternateRowStyles: { fillColor: [248, 250, 252] },
  });

  // ── Footer ────────────────────────────────────────────────────────────────
  const pageCount = doc.internal.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    doc.setFontSize(8);
    doc.setTextColor(150);
    doc.text(`Page ${i} of ${pageCount}`, 195, 285, { align: "right" });
    doc.text("Generated by Clinomic Labs LIS - For Investigational Use Only", 105, 285, { align: "center" });
  }

  return doc;
}


// ── Patient PDF Disclosure Specification (April 2026) — spec_v1 template ──
//
// Implements Block A through Block F per the spec.  All placeholder
// values fall through to ``[TBD]`` (counsel-spec direction) when a
// per-lab readiness audit has not yet supplied them — the per-lab flag
// `Lab.patient_pdf_workflow_recs_enabled` is the operations gate that
// stops a real patient from receiving a [TBD]-laden report.
//
// Layout note: the spec_v1 template renders more text than the legacy
// template and may overflow A4 onto a second page.  jsPDF's autoTable
// handles overflow for tables; fixed-position blocks (Block A header,
// Block E sign-off, Block F footer) use ``_renderFooterBlockF`` per-page
// in a final loop after all autoTables resolve.

const TBD_FALLBACK = "[TBD]";

function _disclosureCfg(result) {
  return result?.disclosureConfig || {};
}

/** Block A — manufacturer identification + beta-phase line.  Sits
 * directly below the lab letterhead bar.  Returns the new bottom Y. */
function _renderBlockA(doc, result) {
  const cfg = _disclosureCfg(result);
  const isProd = cfg.cdsco_registered === true;
  const swVersion = tbd(cfg.software_version);
  const rulesVersion = tbd(cfg.rules_version);

  // Title strip
  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.setTextColor(0, 0, 0);
  doc.text(
    `ClinomicLabs Workflow Recommendations  |  Software v${swVersion}  |  Rules v${rulesVersion}`,
    14, 27,
  );

  // Manufacturer + intended-use lay summary
  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  const manufacturerLine = `AI-powered laboratory workflow software by ${
    cfg.manufacturer_name || "Arogya BioX Pvt Ltd"
  }, ${cfg.manufacturer_city || "Ahmedabad"}.`;
  doc.text(manufacturerLine, 14, 33, { maxWidth: 182 });

  const layIntent =
    "The recommendations on this report do not diagnose any condition. " +
    "They suggest which follow-up laboratory tests your doctor may wish " +
    "to consider. Only your doctor can decide what your results mean for you.";
  const layLines = doc.splitTextToSize(layIntent, 182);
  doc.text(layLines, 14, 38);

  // Beta-phase line OR CDSCO license
  const lineY = 38 + layLines.length * 4 + 2;
  doc.setFont("helvetica", "italic");
  doc.setFontSize(8);
  doc.setTextColor(120, 60, 0);
  if (isProd) {
    doc.text(
      `CDSCO Class A Medical Device License: ${tbd(cfg.cdsco_license_number)}`,
      14, lineY,
    );
  } else {
    doc.text(
      "This software is currently in pre-commercial evaluation. " +
      "It has not yet completed registration with CDSCO.",
      14, lineY, { maxWidth: 182 },
    );
  }
  doc.setTextColor(0, 0, 0);
  doc.setFont("helvetica", "normal");

  return lineY + 4;
}

/** Block C — Workflow Recommendations section banner.  Returns the new
 * Y after the banner block ends. */
function _renderBlockC(doc, y) {
  doc.setDrawColor(13, 148, 136);
  doc.setLineWidth(0.4);
  doc.line(14, y, 196, y);

  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(13, 148, 136);
  doc.text(
    "WORKFLOW RECOMMENDATIONS  •  AI-generated  •  Not a medical diagnosis",
    14, y + 5,
  );
  doc.setTextColor(0, 0, 0);
  doc.line(14, y + 7, 196, y + 7);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  const banner =
    "The suggestions below are generated by AI software based on your CBC " +
    "results. They are NOT a diagnosis. They do NOT mean you have any of " +
    "the conditions named below. Please discuss this report with your " +
    "doctor before drawing any conclusion about your health.";
  const lines = doc.splitTextToSize(banner, 182);
  doc.text(lines, 14, y + 13);
  return y + 13 + lines.length * 4 + 2;
}

/** Block D — patient-facing card stack.  Renders D.4 empty-state when
 * no rules fire and D.5 macrocytic footnote when applicable.  Returns
 * the new Y. */
function _renderBlockD(doc, y, result) {
  const rules = result?.clinicalRules || {};
  const cards = ["iron_deficiency", "thalassemia_trait", "macrocytic_anemia", "anemia_subtype"]
    .map((k) => patientModuleCard(k, rules[k]))
    .filter(Boolean);

  if (cards.length === 0) {
    // D.4 empty-state
    doc.setFillColor(248, 250, 252);
    doc.setDrawColor(226, 232, 240);
    const emptyLines = doc.splitTextToSize(PATIENT_EMPTY_STATE_TEXT, 174);
    const emptyHeight = 6 + emptyLines.length * 4 + 4;
    doc.rect(14, y, 182, emptyHeight, "FD");
    doc.setFont("helvetica", "italic");
    doc.setFontSize(9);
    doc.text(emptyLines, 18, y + 6);
    doc.setFont("helvetica", "normal");
    return y + emptyHeight + 4;
  }

  let cursor = y;
  for (const card of cards) {
    cursor = _renderPatientCard(doc, cursor, card);
  }
  // D.5 footnote — only when the macrocytic card was rendered
  if (cards.some((c) => c.moduleKey === "macrocytic_anemia")) {
    doc.setFont("helvetica", "italic");
    doc.setFontSize(8);
    doc.setTextColor(80);
    const noteLines = doc.splitTextToSize(PATIENT_MACROCYTIC_FOOTNOTE, 182);
    doc.text(noteLines, 14, cursor + 2);
    doc.setTextColor(0, 0, 0);
    doc.setFont("helvetica", "normal");
    cursor += 2 + noteLines.length * 4;
  }
  return cursor + 4;
}

function _renderPatientCard(doc, y, card) {
  // Card border
  doc.setDrawColor(200, 218, 224);
  doc.setFillColor(240, 250, 252);

  const reasoningText = card.reasoning && card.reasoning.length
    ? card.reasoning.join(" • ")
    : "";
  const reasoningLines = reasoningText
    ? doc.splitTextToSize(reasoningText, 174)
    : [];
  const sourceLines = card.source ? doc.splitTextToSize(card.source, 174) : [];
  const titleLines = doc.splitTextToSize(card.title, 130);

  const cardHeight =
    6  // top padding
    + titleLines.length * 5
    + (card.confidenceLabel ? 5 : 0)
    + 1
    + reasoningLines.length * 4
    + 2
    + sourceLines.length * 4
    + 4; // bottom padding

  doc.rect(14, y, 182, cardHeight, "FD");

  // Title
  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.text(titleLines, 18, y + 6);

  // Confidence pill (right-aligned)
  let cursor = y + 6 + titleLines.length * 5;
  if (card.confidenceLabel) {
    doc.setFont("helvetica", "italic");
    doc.setFontSize(8);
    doc.setTextColor(80);
    doc.text(card.confidenceLabel, 192, y + 6, { align: "right" });
    doc.setTextColor(0, 0, 0);
  }

  // Reasoning chips
  if (reasoningLines.length) {
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9);
    doc.text(reasoningLines, 18, cursor);
    cursor += reasoningLines.length * 4 + 2;
  }

  // Source line (small, italic)
  if (sourceLines.length) {
    doc.setFont("helvetica", "italic");
    doc.setFontSize(8);
    doc.setTextColor(100);
    doc.text(sourceLines, 18, cursor);
    doc.setTextColor(0, 0, 0);
    doc.setFont("helvetica", "normal");
  }

  return y + cardHeight + 3;
}

/** Block E — pathologist sign-off panel.  Always rendered.  Missing
 * config falls through to ``[TBD]`` so the readiness audit sees the
 * gap. */
function _renderBlockE(doc, y, result) {
  const cfg = _disclosureCfg(result);
  doc.setDrawColor(180, 180, 180);
  doc.setLineWidth(0.3);
  doc.line(14, y, 196, y);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(80);
  doc.text("Reviewed and approved by:", 14, y + 5);
  doc.setTextColor(0, 0, 0);

  const pathName = `Dr. ${tbd(cfg.pathologist_name)}`;
  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.text(pathName, 14, y + 12);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  const credLine =
    `${tbd(cfg.pathologist_qualification)}  |  Council Reg. No.: ${
      tbd(cfg.pathologist_registration)
    }`;
  doc.text(credLine, 14, y + 17);

  const designationLine =
    `${tbd(cfg.pathologist_designation)}, ${tbd(cfg.lab_name)}`;
  doc.text(designationLine, 14, y + 22);

  // Signature line + date — wet signature applied post-generation OR
  // DSC integration overlays this region.
  doc.setFontSize(9);
  doc.text("Signature: ____________________________", 14, y + 32);
  doc.text("Date: __________", 130, y + 32);

  doc.line(14, y + 38, 196, y + 38);
  return y + 40;
}

/** Block F — mandatory footer.  Reflowed onto every page.  The §8
 * unbreakable line is in here verbatim per the user's directive. */
function _renderFooterBlockF(doc, result, pageIndex, totalPages) {
  const cfg = _disclosureCfg(result);
  const isProd = cfg.cdsco_registered === true;
  // Footer occupies bottom ~50mm of every page.  Anchor to A4 height
  // 297mm; start at 240 and run to 290.  Page-N declaration at the
  // very bottom.
  const top = 240;
  doc.setDrawColor(120, 120, 120);
  doc.setLineWidth(0.5);
  doc.line(14, top, 196, top);
  doc.line(14, top + 1, 196, top + 1);

  doc.setFont("helvetica", "bold");
  doc.setFontSize(8);
  doc.setTextColor(0, 0, 0);
  doc.text("IMPORTANT — PLEASE READ", 14, top + 5);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(7.5);
  const para1 =
    "The Workflow Recommendations on this report are generated by AI " +
    "software. They are NOT a diagnosis. They do NOT confirm or rule out " +
    "any disease, condition, or deficiency.";
  let cursor = top + 9;
  const para1Lines = doc.splitTextToSize(para1, 182);
  doc.text(para1Lines, 14, cursor);
  cursor += para1Lines.length * 3 + 1;

  // §8 unbreakable line — counsel directive
  doc.setFont("helvetica", "bold");
  const para2 =
    "All decisions about your health must be made by a registered medical " +
    "practitioner who knows your full medical history. The vitamin B12 " +
    "blood test, hemoglobin electrophoresis test, and iron studies blood " +
    "test remain the standard laboratory tests for definitive investigation " +
    "of the conditions referenced.";
  const para2Lines = doc.splitTextToSize(para2, 182);
  doc.text(para2Lines, 14, cursor);
  cursor += para2Lines.length * 3 + 1;

  doc.setFont("helvetica", "normal");
  const para3 =
    "If you have received any flag on this report and are concerned, please " +
    "consult your doctor. Do not change your diet, take any supplement, or " +
    "make any health decision based on this report alone.";
  const para3Lines = doc.splitTextToSize(para3, 182);
  doc.text(para3Lines, 14, cursor);
  cursor += para3Lines.length * 3 + 2;

  // Privacy block
  doc.setDrawColor(180, 180, 180);
  doc.setLineWidth(0.2);
  doc.line(14, cursor, 196, cursor);
  cursor += 3;

  doc.setFontSize(7);
  doc.setTextColor(60);
  doc.text(
    "Privacy: Your laboratory data is processed in accordance with the " +
    "Digital Personal Data Protection Act, 2023.",
    14, cursor, { maxWidth: 182 },
  );
  cursor += 5;
  doc.text(`For questions about this report: ${tbd(cfg.grievance_email)}`, 14, cursor);
  cursor += 3;
  doc.text(
    `For privacy questions about how the software handles your data: ${tbd(cfg.dpo_email)}`,
    14, cursor,
  );
  cursor += 3;
  doc.text(`Full Privacy Notice: ${tbd(cfg.privacy_notice_url)}`, 14, cursor);
  cursor += 4;

  // Manufacturer + status line
  const statusLine = isProd
    ? `Software: ClinomicLabs by ${cfg.manufacturer_name || "Arogya BioX Pvt Ltd"}. ` +
      `CDSCO Class A Medical Device License: ${tbd(cfg.cdsco_license_number)}.`
    : `This report is computer-generated. Software: ClinomicLabs by ` +
      `${cfg.manufacturer_name || "Arogya BioX Pvt Ltd"}. ` +
      `Status: Pre-commercial evaluation, CDSCO Class A registration in progress.`;
  doc.text(statusLine, 14, cursor, { maxWidth: 182 });

  // Page footer at the very bottom
  doc.setFontSize(7);
  doc.setTextColor(150);
  doc.text(`Page ${pageIndex} of ${totalPages}`, 195, 292, { align: "right" });
  doc.setTextColor(0, 0, 0);
}

async function _generateReportSpecV1(patient, result, cbcRows) {
  const doc = new jsPDF();

  // ── Lab letterhead bar (kept) ───────────────────────────────────────────
  doc.setFillColor(13, 148, 136);
  doc.rect(0, 0, 210, 20, "F");
  try {
    const logo = await loadImage("/clean-logo.png?v=1");
    doc.addImage(logo, "PNG", 10, 2, 16, 16);
    doc.setDrawColor(255, 255, 255);
    doc.setLineWidth(0.5);
    doc.line(28, 5, 28, 15);
    doc.setTextColor(255, 255, 255);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(18);
    doc.text("Clinomic Labs", 32, 13);
  } catch {
    doc.setTextColor(255, 255, 255);
    doc.setFont("helvetica", "bold");
    doc.setFontSize(18);
    doc.text("Clinomic Labs", 14, 13);
  }
  doc.setFontSize(10);
  doc.setFont("helvetica", "normal");
  doc.text("Vitamin B12 Screening Report", 195, 13, { align: "right" });

  // Block A — manufacturer ID + beta-phase line
  let cursor = _renderBlockA(doc, result);
  cursor += 2;

  // Patient info block
  doc.setTextColor(0, 0, 0);
  doc.setFontSize(10);
  doc.setFont("helvetica", "bold");
  doc.text("Patient Name:", 14, cursor);
  doc.setFont("helvetica", "normal");
  const nameLines = doc.splitTextToSize(patient.name || "N/A", 80);
  doc.text(nameLines, 42, cursor);
  doc.setFont("helvetica", "bold"); doc.text("Date:", 130, cursor);
  doc.setFont("helvetica", "normal"); doc.text(patient.date || "N/A", 142, cursor);
  cursor += 5;

  doc.setFont("helvetica", "bold"); doc.text("Patient ID:", 14, cursor);
  doc.setFont("helvetica", "normal"); doc.text(patient.id || "N/A", 36, cursor);
  doc.setFont("helvetica", "bold"); doc.text("Lab Name:", 130, cursor);
  doc.setFont("helvetica", "normal");
  const labLines = doc.splitTextToSize(patient.labId || "N/A", 50);
  doc.text(labLines, 152, cursor);
  cursor += 5;

  doc.setFont("helvetica", "bold"); doc.text("Age/Sex:", 14, cursor);
  doc.setFont("helvetica", "normal"); doc.text(`${patient.age || "-"} / ${patient.sex || "-"}`, 32, cursor);
  cursor += 4;

  doc.setDrawColor(200, 200, 200);
  doc.setLineWidth(0.1);
  doc.line(14, cursor, 196, cursor);
  cursor += 5;

  // Screening result + clinical narrative
  const labelMap = { 1: "Normal", 2: "Borderline", 3: "Deficient" };
  const colorMap = { 1: [34, 197, 94], 2: [245, 158, 11], 3: [239, 68, 68] };
  const labelText = labelMap[result.label] || "Normal";
  const color = colorMap[result.label] || [34, 197, 94];

  doc.setFontSize(13);
  doc.setFont("helvetica", "normal");
  doc.text("Screening Result:", 14, cursor);
  doc.setFont("helvetica", "bold");
  doc.setTextColor(...color);
  doc.text(labelText, 55, cursor);
  doc.setTextColor(0, 0, 0);
  cursor += 6;

  // Clinical interpretation + recommendation box (legacy content kept)
  doc.setFillColor(248, 250, 252);
  doc.setDrawColor(226, 232, 240);
  doc.rect(14, cursor, 182, 30, "FD");
  doc.setFont("helvetica", "bold");
  doc.setFontSize(9);
  doc.text("Clinical Interpretation:", 18, cursor + 5);
  doc.setFont("helvetica", "normal");
  doc.text(result.interpretation || "", 18, cursor + 10, { maxWidth: 174 });
  doc.setFont("helvetica", "bold");
  doc.text("Recommendation:", 18, cursor + 22);
  doc.setFont("helvetica", "normal");
  doc.text(result.recommendation || "", 18, cursor + 27, { maxWidth: 174 });
  cursor += 34;

  // Indices table — same microcytic-gating as legacy
  const mcvRow = (cbcRows || []).find((r) => r.key === "mcv");
  const mcvValue = parseFloat(mcvRow?.value);
  const isMicrocytic = Number.isFinite(mcvValue) && mcvValue < 80;
  const mentzerSig = isMicrocytic
    ? (result.indices.mentzer > 13 ? "Microcytic + Mentzer > 13: favors IDA over BTT" : "Microcytic + Mentzer < 13: favors BTT")
    : "Discrimination index — only meaningful in microcytic patients";
  const greenKingSig = isMicrocytic
    ? (result.indices.greenKing > 65 ? "Microcytic + G&K > 65: favors IDA over BTT" : "Microcytic + G&K < 65: favors BTT")
    : "Discrimination index — only meaningful in microcytic patients";

  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.text("Hematological Indices", 14, cursor);
  cursor += 3;

  autoTable(doc, {
    startY: cursor,
    head: [["Index", "Value", "Clinical Significance"]],
    body: [
      ["Mentzer Index",               String(result.indices.mentzer),   mentzerSig],
      ["Green & King Index",          String(result.indices.greenKing), greenKingSig],
      ["NLR (Neutrophil/Lymphocyte)", String(result.indices.nlr),       "Inflammatory marker"],
    ],
    theme: "grid",
    headStyles: { fillColor: [13, 148, 136], fontSize: 8, fontStyle: "bold" },
    styles: { fontSize: 7.5, cellPadding: 2 },
    columnStyles: { 0: { fontStyle: "bold", cellWidth: 60 }, 1: { cellWidth: 25 } },
  });
  cursor = doc.lastAutoTable.finalY + 5;

  // CBC table
  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.text("Complete Blood Count (CBC) Data", 14, cursor);
  cursor += 2;
  autoTable(doc, {
    startY: cursor,
    head: [["Test", "Result", "Unit", "Ref. Range"]],
    body: cbcRows.map((row) => [
      row.test,
      row.value || "-",
      row.unit,
      `${(patient.sex === "M" ? row.refRangeM : row.refRangeF).join(" - ")}`,
    ]),
    theme: "striped",
    headStyles: { fillColor: [51, 65, 85], fontSize: 8, fontStyle: "bold" },
    styles: { fontSize: 7.5, cellPadding: 1.5 },
    alternateRowStyles: { fillColor: [248, 250, 252] },
  });
  cursor = doc.lastAutoTable.finalY + 5;

  // Block C banner + Block D cards.  If layout is tight, autoTable's
  // page break will already have flowed; just resume from finalY.
  if (cursor > 180) {
    doc.addPage();
    cursor = 30;
  }
  cursor = _renderBlockC(doc, cursor);
  cursor = _renderBlockD(doc, cursor, result);

  // Block E pathologist sign-off — must fit on the same page; if not,
  // roll to a new page.
  if (cursor > 200) {
    doc.addPage();
    cursor = 30;
  }
  cursor = _renderBlockE(doc, cursor, result);

  // Block F mandatory footer on every page.
  const pageCount = doc.internal.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    _renderFooterBlockF(doc, result, i, pageCount);
  }

  return doc;
}

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

/**
 * Build the result object expected by generateReport() from a full screening record.
 *
 * @param {object} screening - Full screening record from the API.
 * @returns {object}
 */
export function buildResultFromScreening(screening) {
  const riskClass = screening.risk_class;
  let recommendation;
  if (riskClass === 3) {
    recommendation = "Serum B12 measurement recommended. Clinical correlation advised.";
  } else if (riskClass === 2) {
    recommendation = "Consider serum B12 measurement if clinically indicated.";
  } else {
    recommendation = "B12 deficiency unlikely based on CBC parameters.";
  }

  return {
    label: riskClass,
    probabilities: screening.probabilities,
    indices: screening.indices,
    interpretation: (screening.rules_fired || []).join(", "),
    recommendation,
  };
}

const loadImage = (url) =>
  new Promise((resolve, reject) => {
    const img = new Image();
    img.src = url;
    img.onload = () => resolve(img);
    img.onerror = reject;
  });

/**
 * Generate a jsPDF document for a B12 screening report.
 *
 * @param {object} patient  - { name, id, age, sex, date, labId }
 * @param {object} result   - { probabilities, interpretation, recommendation, indices }
 * @param {Array}  cbcRows  - INITIAL_CBC_ROWS-shaped array with .value populated
 * @returns {Promise<jsPDF>}
 */
export async function generateReport(patient, result, cbcRows) {
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
  doc.setFont("helvetica", "bold");
  doc.setFontSize(11);
  doc.text("Hematological Indices", 14, 120);

  autoTable(doc, {
    startY: 124,
    head: [["Index", "Value", "Clinical Significance"]],
    body: [
      ["Mentzer Index",              String(result.indices.mentzer),   result.indices.mentzer > 13 ? "Possible Iron Deficiency" : "Possible Thalassemia"],
      ["Green & King Index",         String(result.indices.greenKing), "Differentiation of IDA vs Thalassemia"],
      ["NLR (Neutrophil/Lymphocyte)", String(result.indices.nlr),      "Inflammatory Marker"],
    ],
    theme: "grid",
    headStyles: { fillColor: [13, 148, 136], fontSize: 9, fontStyle: "bold" },
    styles: { fontSize: 8, cellPadding: 3 },
    columnStyles: { 0: { fontStyle: "bold", cellWidth: 70 }, 1: { cellWidth: 30 } },
  });

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

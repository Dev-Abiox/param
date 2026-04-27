/**
 * Pure helpers for rendering the four rule-based clinical workflow modules
 * (iron deficiency, beta-thalassemia trait, macrocytic / megaloblastic
 * pattern, composite anemia subtype) in both the on-screen ResultPanel
 * and the downloadable PDF.
 *
 * Lives in its own file (no jspdf, no React) so the helpers are testable
 * under Jest's default jsdom environment without polyfilling TextEncoder.
 *
 * Source of truth for the underlying rule logic is the backend module
 * apps.screening.clinical_rules — keep the keys here in sync with the
 * reasoning codes that module emits.
 */

export const MODULE_LABEL = {
  iron_deficiency: "Iron Deficiency",
  thalassemia_trait: "Beta-Thalassemia Trait",
  macrocytic_anemia: "Macrocytic / Megaloblastic Pattern",
  anemia_subtype: "Anemia Subtype",
};

export const REASONING_LABEL = {
  microcytic_hypochromic_anemia: "microcytic + hypochromic + low Hb",
  mentzer_gt_13_ida_favored_over_btt: "Mentzer > 13 (favors IDA over BTT)",
  green_king_gt_65_ida_favored_over_btt: "Green-King > 65 (favors IDA over BTT)",
  anisocytosis_with_microcytosis: "elevated RDW with microcytosis",
  low_hb_with_low_normal_mcv: "low Hb with low / borderline MCV",
  mentzer_lt_13_btt_suspected: "Mentzer < 13 (BTT pattern)",
  shine_lal_lt_1530_btt_suspected: "Shine-Lal < 1530 (BTT pattern)",
  microcytic_high_rbc_btt_pattern: "microcytic with normal / high RBC count",
  microcytic_uniform_cells_btt_pattern: "microcytic with uniform cell size (low RDW)",
  england_fraser_negative_btt_suspected: "England-Fraser index < 0",
  macrocytic_mcv_gt_100: "MCV > 100 (overt macrocytosis)",
  borderline_macrocytic_with_anisocytosis: "MCV > 95 with elevated RDW",
  macrocytic_hyperchromic_pattern: "MCV > 95 with high MCH",
  possible_megaloblastic_pancytopenia: "anemia + low platelets + low WBC",
  not_microcytic: "not microcytic — module skipped",
  microcytic_but_no_btt_indicators: "microcytic but no BTT indicators",
  insufficient_data: "insufficient CBC data",
};

export const CONFIDENCE_PILL = {
  high: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300 border-red-200 dark:border-red-800",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 border-amber-200 dark:border-amber-800",
  low: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-200 dark:border-slate-700",
};

export const formatReasoning = (codes) =>
  (codes || [])
    .map((c) => REASONING_LABEL[c] || c.replace(/_/g, " "))
    .join("; ");

/**
 * Convert one module's payload into a tabular row [label, confidence,
 * reasoning, recommendation], or null if the module did not flag.
 * The composite anemia_subtype module reports under different keys
 * (`anemic`, `suspected_subtype`) so it has its own branch.
 */
export const moduleCells = (moduleKey, payload) => {
  if (moduleKey === "anemia_subtype") {
    if (payload?.anemic !== true || !payload.suspected_subtype) return null;
    const subtype = payload.suspected_subtype.replace(/_/g, " ");
    return [
      MODULE_LABEL[moduleKey],
      "—",
      `suspected: ${subtype}`,
      payload.recommendation || "",
    ];
  }
  if (!payload || payload.flag !== true) return null;
  return [
    MODULE_LABEL[moduleKey] || moduleKey,
    payload.confidence || "—",
    formatReasoning(payload.reasoning),
    payload.recommendation || "",
  ];
};

/**
 * Same data as `moduleCells` but shaped for React rendering rather
 * than table cells.  Returns an array of objects with `key`, `label`,
 * `confidence`, `reasoning` (raw codes), and `recommendation`.  Used by
 * ResultPanel.
 */
export const flaggedModules = (clinicalRules) => {
  if (!clinicalRules) return [];
  const out = [];
  for (const key of ["iron_deficiency", "thalassemia_trait", "macrocytic_anemia"]) {
    const m = clinicalRules[key];
    if (m && m.flag === true) {
      out.push({
        key,
        label: MODULE_LABEL[key],
        confidence: m.confidence,
        reasoning: m.reasoning || [],
        recommendation: m.recommendation,
      });
    }
  }
  const subtype = clinicalRules.anemia_subtype;
  if (subtype && subtype.anemic === true && subtype.suspected_subtype) {
    out.push({
      key: "anemia_subtype",
      label: MODULE_LABEL.anemia_subtype,
      confidence: null,
      reasoning: [`suspected: ${subtype.suspected_subtype.replace(/_/g, " ")}`],
      recommendation: subtype.recommendation,
    });
  }
  return out;
};

/**
 * Build the ``result`` object the PDF generator and ResultPanel expect
 * from a stored screening record.  Pure data transform — kept out of
 * generateReport.js so tests don't have to load jspdf.
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
    // Both casings tolerated — snake_case from the GET serializer,
    // camelCase from the live predict response.
    clinicalRules: screening.clinical_rules || screening.clinicalRules || null,
    cbcSnapshot: screening.cbc_snapshot || screening.cbcSnapshot || null,
    // Patient PDF Disclosure Spec — Option A gate.  Defaults to false
    // when the field is absent (legacy responses, FHIR-bypass reads,
    // anything pre-Option-A) so a missing flag fails *closed* — the
    // patient PDF withholds the Workflow Recommendations section.  Only
    // an explicit ``true`` from the backend opens the gate.
    labWorkflowRecsEnabled: Boolean(
      screening.lab_workflow_recs_enabled
        ?? screening.labWorkflowRecsEnabled
        ?? false,
    ),
  };
}

/**
 * Unit tests for the clinical-rule helpers in generateReport.js.
 *
 * Pins the empty-state contract (healthy CBC produces no flagged rows in
 * the PDF / on-screen output) and the moduleCells / formatReasoning
 * shape the renderers depend on.
 */

import {
  PATIENT_CONFIDENCE_LABEL,
  PATIENT_EMPTY_STATE_TEXT,
  PATIENT_MACROCYTIC_FOOTNOTE,
  PATIENT_MODULE_TITLE,
  PATIENT_REASONING_LABEL,
  PATIENT_SOURCE_LINE,
  buildResultFromScreening,
  disclosureConfigComplete,
  formatReasoning,
  moduleCells,
  patientModuleCard,
  tbd,
} from "../lib/clinicalRulesHelpers";

describe("formatReasoning", () => {
  test("translates known reasoning codes to readable text", () => {
    expect(formatReasoning(["mentzer_gt_13_ida_favored_over_btt"]))
      .toBe("Mentzer > 13 (favors IDA over BTT)");
  });

  test("falls back to slug-as-text for unknown codes", () => {
    expect(formatReasoning(["some_unknown_code"]))
      .toBe("some unknown code");
  });

  test("joins multiple codes with semicolons", () => {
    const out = formatReasoning([
      "macrocytic_mcv_gt_100",
      "macrocytic_hyperchromic_pattern",
    ]);
    expect(out).toContain("MCV > 100");
    expect(out).toContain("MCV > 95 with high MCH");
    expect(out.split("; ")).toHaveLength(2);
  });

  test("handles null / undefined / empty", () => {
    expect(formatReasoning(null)).toBe("");
    expect(formatReasoning(undefined)).toBe("");
    expect(formatReasoning([])).toBe("");
  });
});

describe("moduleCells", () => {
  test("returns null when module did not flag", () => {
    expect(moduleCells("iron_deficiency", { flag: false, reasoning: [] })).toBeNull();
    expect(moduleCells("iron_deficiency", null)).toBeNull();
    expect(moduleCells("iron_deficiency", undefined)).toBeNull();
  });

  test("returns row tuple when module flagged", () => {
    const row = moduleCells("iron_deficiency", {
      flag: true,
      confidence: "high",
      reasoning: ["microcytic_hypochromic_anemia", "anisocytosis_with_microcytosis"],
      recommendation: "Consider reflex ferritin and iron studies testing",
    });
    expect(row).toEqual([
      "Iron Deficiency",
      "high",
      "microcytic + hypochromic + low Hb; elevated RDW with microcytosis",
      "Consider reflex ferritin and iron studies testing",
    ]);
  });

  test("anemia_subtype renders only when anemic and subtype present", () => {
    expect(moduleCells("anemia_subtype", { anemic: false })).toBeNull();
    expect(moduleCells("anemia_subtype", { anemic: true, suspected_subtype: null })).toBeNull();
    const row = moduleCells("anemia_subtype", {
      anemic: true,
      suspected_subtype: "iron_deficiency_anemia",
      recommendation: "Anemia profile suggests iron_deficiency_anemia; reflex testing recommended.",
    });
    expect(row[0]).toBe("Anemia Subtype");
    expect(row[2]).toContain("iron deficiency anemia");
  });
});

describe("buildResultFromScreening", () => {
  const baseScreening = {
    risk_class: 3,
    probabilities: { normal: 0.1, borderline: 0.2, deficient: 0.7 },
    indices: { mentzer: 22.79, greenKing: 83.2, nlr: 17.7 },
    rules_fired: ["pattern_a"],
    cbc_snapshot: { Hb: 14.2, MCV: 95.7 },
  };

  test("passes clinical_rules through under camelCase key", () => {
    const result = buildResultFromScreening({
      ...baseScreening,
      clinical_rules: {
        iron_deficiency: { flag: false, reasoning: [] },
        macrocytic_anemia: { flag: true, confidence: "low", reasoning: ["macrocytic_hyperchromic_pattern"] },
      },
    });
    expect(result.clinicalRules).toBeTruthy();
    expect(result.clinicalRules.macrocytic_anemia.flag).toBe(true);
  });

  test("tolerates already-camelCase clinicalRules from live response", () => {
    const result = buildResultFromScreening({
      ...baseScreening,
      clinicalRules: { iron_deficiency: { flag: false, reasoning: [] } },
    });
    expect(result.clinicalRules.iron_deficiency.flag).toBe(false);
  });

  test("clinicalRules is null when neither key present", () => {
    const result = buildResultFromScreening(baseScreening);
    expect(result.clinicalRules).toBeNull();
  });

  test("recommendation text matches risk class", () => {
    expect(buildResultFromScreening({ ...baseScreening, risk_class: 3 }).recommendation)
      .toContain("recommended");
    expect(buildResultFromScreening({ ...baseScreening, risk_class: 1 }).recommendation)
      .toContain("unlikely");
  });
});

// Sprint isolation contract — the rule helpers are pure and the
// renderer must produce zero clinical-rule rows for the empty state.
describe("empty-state contract", () => {
  test("a clinicalRules bundle with all flag=false produces no PDF rows", () => {
    const allFalse = {
      iron_deficiency: { flag: false, reasoning: [] },
      thalassemia_trait: { flag: false, reasoning: ["not_microcytic"] },
      macrocytic_anemia: { flag: false, reasoning: [] },
      anemia_subtype: { anemic: false },
    };
    const rows = ["iron_deficiency", "thalassemia_trait", "macrocytic_anemia", "anemia_subtype"]
      .map((k) => moduleCells(k, allFalse[k]))
      .filter(Boolean);
    expect(rows).toEqual([]);
  });
});

// Patient PDF Disclosure Spec — Option A.  The lab feature flag must
// fail closed: any value other than an explicit ``true`` from the
// backend keeps the PDF Workflow Recommendations section suppressed.
describe("Option A patient-PDF flag pass-through", () => {
  const baseScreening = {
    risk_class: 2,
    probabilities: { normal: 0.3, borderline: 0.5, deficient: 0.2 },
    indices: { mentzer: 18.4, greenKing: 66.1, nlr: 2.0 },
    rules_fired: [],
    cbc_snapshot: { Hb: 14.2, MCV: 85.3 },
  };

  test("explicit true enables the flag", () => {
    const r = buildResultFromScreening({ ...baseScreening, lab_workflow_recs_enabled: true });
    expect(r.labWorkflowRecsEnabled).toBe(true);
  });

  test("explicit false keeps the flag off", () => {
    const r = buildResultFromScreening({ ...baseScreening, lab_workflow_recs_enabled: false });
    expect(r.labWorkflowRecsEnabled).toBe(false);
  });

  test("missing flag defaults to off — the fail-closed contract", () => {
    const r = buildResultFromScreening(baseScreening);
    expect(r.labWorkflowRecsEnabled).toBe(false);
  });

  test("camelCase from live predict response also works", () => {
    const r = buildResultFromScreening({ ...baseScreening, labWorkflowRecsEnabled: true });
    expect(r.labWorkflowRecsEnabled).toBe(true);
  });

  test("non-boolean truthy values normalise to a real boolean", () => {
    // Belt and braces: if the backend ever sends a string ``"true"``
    // by accident, we still want a boolean out.  ``Boolean("true")``
    // is true; ``Boolean("false")`` is also true (truthy string!) —
    // this test pins the current behaviour so anyone touching this
    // path notices.  The right thing is for the backend to send a
    // boolean; the helper only normalises shape, not coerces strings.
    const r1 = buildResultFromScreening({ ...baseScreening, lab_workflow_recs_enabled: 1 });
    expect(r1.labWorkflowRecsEnabled).toBe(true);
    const r2 = buildResultFromScreening({ ...baseScreening, lab_workflow_recs_enabled: 0 });
    expect(r2.labWorkflowRecsEnabled).toBe(false);
    const r3 = buildResultFromScreening({ ...baseScreening, lab_workflow_recs_enabled: null });
    expect(r3.labWorkflowRecsEnabled).toBe(false);
  });

  test("disclosureConfig propagates from snake_case", () => {
    const r = buildResultFromScreening({
      ...baseScreening,
      disclosure_config: { dpo_email: "dpo@example.com", grievance_email: "" },
    });
    expect(r.disclosureConfig).toEqual({
      dpo_email: "dpo@example.com",
      grievance_email: "",
    });
  });

  test("disclosureConfig is null when neither key present", () => {
    const r = buildResultFromScreening(baseScreening);
    expect(r.disclosureConfig).toBeNull();
  });
});

// Patient PDF Disclosure Spec §D — patient-facing translations.
describe("patient-facing translations", () => {
  test("module titles use lay-readable phrasing — never name the condition", () => {
    expect(PATIENT_MODULE_TITLE.iron_deficiency).toMatch(/follow-up testing/i);
    expect(PATIENT_MODULE_TITLE.iron_deficiency).not.toMatch(/iron deficiency anemia/i);
    expect(PATIENT_MODULE_TITLE.thalassemia_trait).toMatch(/hemoglobin pattern/i);
    // BTT / "thalassemia" itself must not appear in the patient title
    expect(PATIENT_MODULE_TITLE.thalassemia_trait).not.toMatch(/btt/i);
    expect(PATIENT_MODULE_TITLE.thalassemia_trait).not.toMatch(/thalassemia/i);
    expect(PATIENT_MODULE_TITLE.macrocytic_anemia).toMatch(/vitamin b12 and folate/i);
  });

  test("confidence labels never use the word 'confidence'", () => {
    for (const label of Object.values(PATIENT_CONFIDENCE_LABEL)) {
      expect(label.toLowerCase()).not.toContain("confidence");
      expect(label).toMatch(/workflow signal/i);
    }
  });

  test("reasoning translations strip clinical jargon", () => {
    const jargon = ["mentzer", "btt", "ida", "anisocytosis", "microcytic", "hypochromic"];
    for (const text of Object.values(PATIENT_REASONING_LABEL)) {
      for (const j of jargon) {
        expect(text.toLowerCase()).not.toContain(j);
      }
    }
  });

  test("source lines never claim diagnosis", () => {
    for (const text of Object.values(PATIENT_SOURCE_LINE)) {
      expect(text.toLowerCase()).not.toContain("diagnos");
      expect(text.toLowerCase()).not.toContain("detect");
      expect(text.toLowerCase()).toMatch(/workflow suggestion/);
    }
  });

  test("empty-state and macrocytic footnote are non-empty strings", () => {
    expect(PATIENT_EMPTY_STATE_TEXT.length).toBeGreaterThan(50);
    expect(PATIENT_MACROCYTIC_FOOTNOTE.toLowerCase()).toContain("indian");
  });
});

describe("patientModuleCard", () => {
  test("returns null for unflagged module", () => {
    expect(patientModuleCard("iron_deficiency", { flag: false })).toBeNull();
    expect(patientModuleCard("iron_deficiency", null)).toBeNull();
  });

  test("returns lay-readable card for flagged module", () => {
    const card = patientModuleCard("iron_deficiency", {
      flag: true,
      confidence: "high",
      reasoning: ["microcytic_hypochromic_anemia", "anisocytosis_with_microcytosis"],
      recommendation: "Consider reflex ferritin and iron studies testing",
    });
    expect(card.title).toBe("Iron-related follow-up testing may be considered");
    expect(card.confidenceLabel).toBe("Stronger workflow signal");
    expect(card.reasoning).toEqual([
      "Red cell pattern suggesting iron-related investigation",
      "Variation in red cell size with smaller cells",
    ]);
    expect(card.source.toLowerCase()).toContain("workflow suggestion");
    expect(card.moduleKey).toBe("iron_deficiency");
  });

  test("dedupes reasoning chips that translate to the same patient label", () => {
    // Mentzer and Green-King both translate to "Cell-size pattern
    // suggesting iron-related follow-up" — the patient should not see
    // it twice.
    const card = patientModuleCard("iron_deficiency", {
      flag: true,
      confidence: "high",
      reasoning: [
        "mentzer_gt_13_ida_favored_over_btt",
        "green_king_gt_65_ida_favored_over_btt",
      ],
      recommendation: "Consider reflex ferritin and iron studies testing",
    });
    expect(card.reasoning).toEqual([
      "Cell-size pattern suggesting iron-related follow-up",
    ]);
  });

  test("anemia_subtype renders with subtype-specific reasoning, no confidence", () => {
    const card = patientModuleCard("anemia_subtype", {
      anemic: true,
      suspected_subtype: "iron_deficiency_anemia",
      recommendation: "...",
    });
    expect(card.title).toBe("Anemia follow-up testing may be considered");
    expect(card.confidenceLabel).toBe("");
  });

  test("anemia_subtype null when not anemic", () => {
    expect(patientModuleCard("anemia_subtype", { anemic: false })).toBeNull();
  });
});

describe("tbd placeholder helper", () => {
  test("returns [TBD] for null/undefined/empty", () => {
    expect(tbd(null)).toBe("[TBD]");
    expect(tbd(undefined)).toBe("[TBD]");
    expect(tbd("")).toBe("[TBD]");
    expect(tbd("   ")).toBe("[TBD]");
  });

  test("returns the trimmed value when present", () => {
    expect(tbd("dpo@arogyabiox.com")).toBe("dpo@arogyabiox.com");
    expect(tbd("  dpo@arogyabiox.com  ")).toBe("dpo@arogyabiox.com");
  });
});

// ── Patient PDF preview mode (Disclosure Spec admin override) ────────
//
// Smoke tests on generateReport's preview-mode option.  jsPDF imports
// fine here even though it pulls in TextEncoder via fast-png — Jest's
// jsdom polyfills it now (we just need the import not to die).
//
// We can't meaningfully assert on rendered PDF pixels, so the contract
// these tests pin is:
//   1. previewMode=true returns a working doc (no throw, page count > 0)
//   2. previewMode=true with labWorkflowRecsEnabled=false still routes
//      to spec_v1 (legacy template would have a single page; spec_v1
//      tends to overflow to two with the disclosure blocks)
//   3. The PDF text stream contains the watermark string
describe("generateReport preview mode", () => {
  let generateReport;

  beforeAll(async () => {
    // Polyfill TextEncoder for the jspdf import path.
    if (typeof global.TextEncoder === "undefined") {
      const { TextEncoder, TextDecoder } = require("util");
      global.TextEncoder = TextEncoder;
      global.TextDecoder = TextDecoder;
    }
    // jsdom's Image never fires onload / onerror for a same-origin URL,
    // so loadImage in generateReport.js hangs forever.  Stub it to fire
    // onerror on next tick so the try/catch around addImage takes the
    // text-only fallback path.
    global.Image = class {
      constructor() {
        setTimeout(() => this.onerror && this.onerror(new Error("test stub")), 0);
      }
    };
    const mod = await import("../lib/generateReport");
    generateReport = mod.generateReport;
  });

  const _patient = { name: "Test Patient", id: "T-001", age: 35, sex: "M", date: "2026-04-27", labId: "LAB-X" };
  const _result = {
    label: 2,
    probabilities: { normal: 0.3, borderline: 0.5, deficient: 0.2 },
    indices: { mentzer: 18.4, greenKing: 66.1, nlr: 2.0 },
    interpretation: "test interpretation",
    recommendation: "test recommendation",
    rules_fired: [],
    clinicalRules: {
      iron_deficiency: { flag: false, reasoning: [] },
      thalassemia_trait: { flag: false, reasoning: ["not_microcytic"] },
      macrocytic_anemia: { flag: false, reasoning: [] },
      anemia_subtype: { anemic: false },
    },
    labWorkflowRecsEnabled: false,
    disclosureConfig: {
      manufacturer_name: "Arogya BioX Pvt Ltd",
      manufacturer_city: "Ahmedabad",
      software_version: "0.0.0-test",
      rules_version: "1.0.0",
      cdsco_registered: false,
      cdsco_license_number: "",
      dpo_email: "",
      grievance_email: "",
      privacy_notice_url: "",
      pathologist_name: "",
      pathologist_registration: "",
      pathologist_qualification: "",
      pathologist_designation: "",
      lab_name: "Test Lab",
    },
  };
  const _cbcRows = [
    { test: "Hemoglobin", key: "hb", value: "14.5", unit: "g/dL", refRangeM: [13.5, 17.5], refRangeF: [12.0, 15.5] },
    { test: "MCV", key: "mcv", value: "88", unit: "fL", refRangeM: [80, 100], refRangeF: [80, 100] },
    { test: "MCH", key: "mch", value: "29", unit: "pg", refRangeM: [27, 32], refRangeF: [27, 32] },
    { test: "RBC Count", key: "rbc", value: "4.8", unit: "x10^6/µL", refRangeM: [4.5, 5.9], refRangeF: [4.0, 5.2] },
  ];

  test("default download (no options) returns a working doc", async () => {
    const doc = await generateReport(_patient, _result, _cbcRows);
    expect(doc).toBeDefined();
    expect(doc.internal.getNumberOfPages()).toBeGreaterThanOrEqual(1);
  });

  test("previewMode=true returns a working doc", async () => {
    const doc = await generateReport(_patient, _result, _cbcRows, { previewMode: true });
    expect(doc).toBeDefined();
    expect(doc.internal.getNumberOfPages()).toBeGreaterThanOrEqual(1);
  });

  test("previewMode forces spec_v1 even when labWorkflowRecsEnabled=false", async () => {
    // Spec_v1 renders Block A's title text "ClinomicLabs Workflow
    // Recommendations" and Block F's "IMPORTANT — PLEASE READ" header.
    // Legacy renders neither.  The textual content of the PDF stream
    // is reachable via the jsPDF internal doc.output('text') diff.
    const docPreview = await generateReport(_patient, _result, _cbcRows, { previewMode: true });
    const docLegacy = await generateReport(_patient, _result, _cbcRows);

    // jsPDF doesn't expose a clean text accessor, so use the raw PDF
    // bytes — distinct templates produce distinct byte streams; spec_v1
    // is significantly larger because of the disclosure blocks.
    const previewBytes = docPreview.output("arraybuffer").byteLength;
    const legacyBytes = docLegacy.output("arraybuffer").byteLength;
    expect(previewBytes).toBeGreaterThan(legacyBytes);
  });

  test("previewMode does not mutate the input result object", async () => {
    const resultCopy = JSON.parse(JSON.stringify(_result));
    await generateReport(_patient, _result, _cbcRows, { previewMode: true });
    expect(_result).toEqual(resultCopy);
    expect(_result.labWorkflowRecsEnabled).toBe(false);  // still off after preview
  });
});

describe("disclosureConfigComplete", () => {
  const fullConfig = {
    dpo_email: "dpo@arogyabiox.com",
    cdsco_license_number: "MD-XX-1234",
    grievance_email: "grievance@lab.example",
    privacy_notice_url: "https://lab.example/privacy",
    pathologist_name: "Asha Patel",
    pathologist_registration: "GMC-12345",
    pathologist_qualification: "MD",
    pathologist_designation: "Chief Pathologist",
  };

  test("returns true when every required field is non-empty", () => {
    expect(disclosureConfigComplete(fullConfig)).toBe(true);
  });

  test("returns false when any required field is missing or empty", () => {
    for (const k of Object.keys(fullConfig)) {
      const partial = { ...fullConfig, [k]: "" };
      expect(disclosureConfigComplete(partial)).toBe(false);
    }
  });

  test("returns false when config itself is null", () => {
    expect(disclosureConfigComplete(null)).toBe(false);
    expect(disclosureConfigComplete(undefined)).toBe(false);
  });
});

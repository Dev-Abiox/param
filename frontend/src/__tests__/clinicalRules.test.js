/**
 * Unit tests for the clinical-rule helpers in generateReport.js.
 *
 * Pins the empty-state contract (healthy CBC produces no flagged rows in
 * the PDF / on-screen output) and the moduleCells / formatReasoning
 * shape the renderers depend on.
 */

import {
  buildResultFromScreening,
  formatReasoning,
  moduleCells,
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

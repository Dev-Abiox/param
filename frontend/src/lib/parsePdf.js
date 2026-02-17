import * as pdfjsLib from "pdfjs-dist/legacy/build/pdf";
import pdfjsWorker from "pdfjs-dist/legacy/build/pdf.worker.entry";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

/**
 * Extract CBC values and patient info from a lab report PDF.
 * Returns { cbc: { hb, rbc, ... }, patient: { name, age, sex, id } }
 * Only includes fields that were successfully extracted.
 */
export async function parsePdf(file) {
  const arrayBuffer = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;

  // Extract text from all pages, preserving line structure
  const lines = [];
  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const content = await page.getTextContent();

    // Group text items by Y position with tolerance (±3px)
    const yGroups = [];
    for (const item of content.items) {
      if (!item.str || !item.str.trim()) continue;
      const y = item.transform[5];
      const x = item.transform[4];

      // Find existing group within tolerance
      let found = false;
      for (const group of yGroups) {
        if (Math.abs(group.y - y) <= 3) {
          group.items.push({ x, str: item.str });
          // Update group Y to average for better clustering
          group.y = (group.y + y) / 2;
          found = true;
          break;
        }
      }
      if (!found) {
        yGroups.push({ y, items: [{ x, str: item.str }] });
      }
    }

    // Sort by Y (descending = top to bottom) then items by X (left to right)
    yGroups.sort((a, b) => b.y - a.y);
    for (const group of yGroups) {
      group.items.sort((a, b) => a.x - b.x);
      const lineText = group.items.map((it) => it.str).join(" ");
      if (lineText.trim()) lines.push(lineText.trim());
    }
  }

  const fullText = lines.join("\n");

  // Debug: log extracted text to console for troubleshooting
  console.log("PDF extracted lines:", lines);
  console.log("PDF extracted text (first 3000 chars):", fullText.substring(0, 3000));

  const cbc = extractCBCValues(lines, fullText);
  const patient = extractPatientInfo(fullText);

  console.log("Extracted CBC:", cbc);
  console.log("Extracted patient:", patient);

  return { cbc, patient };
}

/**
 * Given a line that matches a CBC label, extract the result value.
 * Lab reports typically have: Label ... Result ... Unit ... Reference Range
 * We want the Result — usually the first number after the label, but NOT
 * serial numbers (like "1." at start) or reference range numbers (like "12.0 - 16.0").
 */
function extractValueFromLine(line, labelPattern) {
  // Remove the label portion to focus on what comes after
  const labelMatch = line.match(labelPattern);
  if (!labelMatch) return undefined;

  const labelEnd = labelMatch.index + labelMatch[0].length;
  const afterLabel = line.substring(labelEnd);

  // Extract all numbers from the portion after the label
  const numbers = afterLabel.match(/\d+\.?\d*/g);
  if (!numbers || numbers.length === 0) return undefined;

  // The first number after the label is typically the result value
  const val = parseFloat(numbers[0]);
  if (!isNaN(val) && val > 0) return val;

  return undefined;
}

/**
 * Search lines for a label and extract the result value.
 * Uses smarter extraction that looks for value AFTER the label text.
 */
function findValueInLines(lines, labelPatterns, range) {
  for (const line of lines) {
    for (const pattern of labelPatterns) {
      if (pattern.test(line)) {
        // Reset lastIndex for global-capable patterns
        pattern.lastIndex = 0;

        const val = extractValueFromLine(line, pattern);
        if (val !== undefined) {
          // Check if value is in expected clinical range
          if (val >= range[0] && val <= range[1]) {
            return val;
          }
          // Handle unit conversions:
          // WBC sometimes reported as 8500 instead of 8.5 (×10³/µL)
          // PLT sometimes reported as 250000 instead of 250
          if (range[1] <= 50 && val > 100 && val / 1000 >= range[0] && val / 1000 <= range[1]) {
            return val / 1000;
          }
          if (range[1] <= 1000 && val > 10000 && val / 1000 >= range[0] && val / 1000 <= range[1]) {
            return Math.round(val / 1000);
          }
        }
      }
    }
  }
  return undefined;
}

// CBC parameter definitions with label patterns and clinical ranges
// Note: patterns avoid trailing \b after optional groups to match plurals (e.g. "Platelets")
const CBC_MAPPINGS = [
  {
    key: "hb",
    patterns: [
      /\b(?:Haemoglobin|Hemoglobin|Hb|HGB)\b/i,
    ],
    range: [3, 25],
  },
  {
    key: "rbc",
    patterns: [
      /\b(?:Red\s*Blood\s*Cell|RBC|Erythrocyte)s?\s*(?:Count)?/i,
      /\bTotal\s*(?:RBC|R\s*\.?\s*B\s*\.?\s*C\s*\.?|Red\s*Blood\s*Cell|Erythrocyte)/i,
      /\bR\s*\.?\s*B\s*\.?\s*C\s*\.?/i,
    ],
    range: [1, 10],
  },
  {
    key: "wbc",
    patterns: [
      /\b(?:White\s*Blood\s*Cell|WBC|Leucocyte|Leukocyte)s?\s*(?:Count)?/i,
      /\bTotal\s*(?:WBC|W\s*\.?\s*B\s*\.?\s*C\s*\.?|White\s*Blood|Leucocyte|Leukocyte)\s*(?:Count)?/i,
      /\bW\s*\.?\s*B\s*\.?\s*C\s*\.?/i,
      /\bTLC\b/i,
      /\bTotal\s*Leu[ck]ocyte\s*Count/i,
    ],
    range: [1, 50],
  },
  {
    key: "plt",
    patterns: [
      /\bPlatelets?\s*(?:Count)?/i,
      /\bPLT\b/i,
      /\bThrombocytes?\s*(?:Count)?/i,
    ],
    range: [10, 1000],
  },
  {
    key: "hct",
    patterns: [
      /\b(?:Hematocrit|Haematocrit|HCT)\b/i,
      /\bP\s*\.?\s*C\s*\.?\s*V\s*\.?/i,
      /\bPacked\s*Cell\s*Volume/i,
    ],
    range: [15, 65],
  },
  {
    key: "mcv",
    patterns: [
      /\bMCV\b/i,
      /\bM\s*\.?\s*C\s*\.?\s*V\s*\.?/i,
      /\bMean\s*(?:Corpuscular|Cell)\s*Volume/i,
    ],
    range: [50, 150],
  },
  {
    key: "mchc",
    patterns: [
      /\bMCHC\b/i,
      /\bM\s*\.?\s*C\s*\.?\s*H\s*\.?\s*C\s*\.?/i,
      /\bMean\s*(?:Corpuscular|Cell)\s*Hemo?globin\s*Conc/i,
    ],
    range: [25, 40],
  },
  {
    key: "mch",
    patterns: [
      /\bMCH\b(?!\s*C)/i,
      /\bM\s*\.?\s*C\s*\.?\s*H\s*\.?\s*(?!C)/i,
      /\bMean\s*(?:Corpuscular|Cell)\s*Hemo?globin\b(?!\s*Conc)/i,
    ],
    range: [15, 45],
  },
  {
    key: "rdw",
    patterns: [
      /\bRDW[\s-]*(?:CV|SD)?/i,
      /\bR\s*\.?\s*D\s*\.?\s*W\s*\.?/i,
      /\bRed\s*(?:Cell\s*)?Distribution\s*Width/i,
    ],
    range: [8, 30],
  },
  {
    key: "neu_pct",
    patterns: [
      /\bNeutrophils?\s*(?:[:%]|percent)?/i,
      /\bNEUT(?:RO)?S?\b/i,
      /\bSegmented\s*Neutrophil/i,
      /\bPolymorphs?\b/i,
    ],
    range: [5, 95],
  },
  {
    key: "lym_pct",
    patterns: [
      /\bLymphocytes?\s*(?:[:%]|percent)?/i,
      /\bLYMPH?S?\b/i,
    ],
    range: [2, 80],
  },
];

function extractCBCValues(lines, fullText) {
  const cbc = {};

  // Strategy 1: Line-based extraction (most common)
  for (const { key, patterns, range } of CBC_MAPPINGS) {
    const val = findValueInLines(lines, patterns, range);
    if (val !== undefined) {
      cbc[key] = val;
    }
  }

  // Strategy 2: If line-based missed values, try adjacent lines
  // Some PDFs split label and value across lines
  if (Object.keys(cbc).length < 5) {
    for (const { key, patterns, range } of CBC_MAPPINGS) {
      if (cbc[key] !== undefined) continue;

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        let matched = false;
        for (const pattern of patterns) {
          if (pattern.test(line)) {
            pattern.lastIndex = 0;
            matched = true;
            break;
          }
        }
        if (!matched) continue;

        // Check if value is on the same line (maybe we missed it due to range)
        const nums = line.match(/\d+\.?\d*/g);
        if (nums) {
          for (const n of nums) {
            const v = parseFloat(n);
            if (v >= range[0] && v <= range[1]) {
              cbc[key] = v;
              break;
            }
            // Unit conversion
            if (range[1] <= 50 && v > 100 && v / 1000 >= range[0] && v / 1000 <= range[1]) {
              cbc[key] = v / 1000;
              break;
            }
            if (range[1] <= 1000 && v > 10000 && v / 1000 >= range[0] && v / 1000 <= range[1]) {
              cbc[key] = Math.round(v / 1000);
              break;
            }
          }
        }
        if (cbc[key] !== undefined) break;

        // Check next line for value (label on one line, value on next)
        if (i + 1 < lines.length) {
          const nextLine = lines[i + 1];
          const nextNums = nextLine.match(/^\s*(\d+\.?\d*)/);
          if (nextNums) {
            const v = parseFloat(nextNums[1]);
            if (v >= range[0] && v <= range[1]) {
              cbc[key] = v;
              break;
            }
          }
        }
      }
    }
  }

  // Strategy 3: Flat text regex extraction (last resort)
  if (Object.keys(cbc).length < 5) {
    for (const { key, patterns, range } of CBC_MAPPINGS) {
      if (cbc[key] !== undefined) continue;
      for (const pattern of patterns) {
        const source = pattern.source;
        // Match label followed by any non-digit chars, then the value
        const regex = new RegExp(source + "[^\\d]*?(\\d+\\.?\\d*)", "i");
        const match = fullText.match(regex);
        if (match) {
          let val = parseFloat(match[1]);
          if (!isNaN(val) && val > 0) {
            // Try unit conversion
            if (val >= range[0] && val <= range[1]) {
              cbc[key] = val;
              break;
            }
            if (range[1] <= 50 && val > 100 && val / 1000 >= range[0] && val / 1000 <= range[1]) {
              cbc[key] = val / 1000;
              break;
            }
            if (range[1] <= 1000 && val > 10000 && val / 1000 >= range[0] && val / 1000 <= range[1]) {
              cbc[key] = Math.round(val / 1000);
              break;
            }
          }
        }
      }
    }
  }

  return cbc;
}

function extractPatientInfo(text) {
  const patient = {};

  // Patient Name — expanded patterns for Indian lab reports
  const namePatterns = [
    /Patient\s*(?:'s\s*)?Name\s*[:\-]\s*([A-Za-z\s.,']+?)(?:\s{2,}|\n|Age|Sex|Gender|Patient\s*ID|DOB|Date|Ref|Sample|Lab|Barcode)/i,
    /Name\s+of\s+(?:the\s+)?Patient\s*[:\-]\s*([A-Za-z\s.,']+?)(?:\s{2,}|\n|Age|Sex|Gender)/i,
    /(?:Client|Pt|Pat)\.?\s*Name\s*[:\-]\s*([A-Za-z\s.,']+?)(?:\s{2,}|\n|Age|Sex|Gender)/i,
    /Name\s*[:\-]\s*(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Master|Baby)?\s*([A-Za-z\s.,']+?)(?:\s{2,}|\n|Age|Sex|Gender|Patient\s*ID|DOB|Date)/i,
    /Name\s*[:\-]\s*([A-Za-z\s.,']+?)(?:\s{2,}|\n|Age|Sex|Gender|Patient\s*ID|DOB|Date)/i,
  ];
  for (const regex of namePatterns) {
    const match = text.match(regex);
    if (match && match[1].trim().length > 1) {
      let name = match[1].trim();
      // Clean up trailing whitespace and common suffixes
      name = name.replace(/\s+(Age|Sex|Gender|DOB|Date|Ref|Sample|Lab).*$/i, "").trim();
      if (name.length > 1 && name.length < 80) {
        patient.name = name;
        break;
      }
    }
  }

  // Age — expanded patterns
  const agePatterns = [
    /Age\s*[/&]\s*(?:Sex|Gender)\s*[:\-]\s*(\d{1,3})\s*(?:yrs?|years?|Y|Yrs|months?|M)?\.?\s*[/\\|,\s]+\s*(M(?:ale)?|F(?:emale)?)/i,
    /Age\s*[:\-]\s*(\d{1,3})\s*(?:yrs?|years?|Y|Yrs)?/i,
    /(\d{1,3})\s*(?:yrs?|years?|Y)\s*[/\\|,\s]+\s*(M(?:ale)?|F(?:emale)?)/i,
    /Age\s*[:\-]?\s*(\d{1,3})\s*(?:yrs?|years?|Y|Yrs)?\s*(?:Sex|Gender)\s*[:\-]?\s*(Male|Female|M|F)/i,
  ];
  for (const regex of agePatterns) {
    const match = text.match(regex);
    if (match) {
      const age = parseInt(match[1], 10);
      if (age > 0 && age < 150) {
        patient.age = age;
        if (match[2]) {
          patient.sex = match[2].charAt(0).toUpperCase() === "M" ? "M" : "F";
        }
        break;
      }
    }
  }

  // Sex (if not already extracted)
  if (!patient.sex) {
    const sexPatterns = [
      /(?:Sex|Gender)\s*[:\-]\s*(Male|Female|M|F)\b/i,
      /\b(Male|Female)\b/i,
    ];
    for (const regex of sexPatterns) {
      const match = text.match(regex);
      if (match) {
        patient.sex = match[1].charAt(0).toUpperCase() === "M" ? "M" : "F";
        break;
      }
    }
  }

  // Patient ID — expanded patterns for Indian labs
  const idPatterns = [
    /(?:Patient\s*ID|MRN|Reg(?:istration)?\.?\s*No\.?|UHID|Lab\s*(?:No\.?|ID)|Sample\s*(?:No\.?|ID)|Barcode\s*(?:No\.?)?|Accession\s*(?:No\.?)?|Bill\s*No\.?|SID|Report\s*(?:No\.?|ID)|OPD\s*No\.?|IPD\s*No\.?|Visit\s*(?:No\.?|ID))\s*[:\-#]?\s*([A-Za-z0-9\-/]+)/i,
  ];
  for (const regex of idPatterns) {
    const match = text.match(regex);
    if (match && match[1].trim().length > 1) {
      patient.id = match[1].trim();
      break;
    }
  }

  return patient;
}

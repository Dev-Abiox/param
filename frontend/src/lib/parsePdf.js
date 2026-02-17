import * as pdfjsLib from "pdfjs-dist/legacy/build/pdf";
import pdfjsWorker from "pdfjs-dist/legacy/build/pdf.worker.entry";
import Tesseract from "tesseract.js";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

/**
 * Extract CBC values and patient info from a lab report PDF.
 * Uses pdfjs for digital PDFs, falls back to Tesseract OCR for scanned PDFs.
 * Returns { cbc: { hb, rbc, ... }, patient: { name, age, sex, id } }
 */
export async function parsePdf(file, onProgress) {
  const arrayBuffer = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;

  // Try digital text extraction first
  let lines = await extractDigitalText(pdf);

  // If no text found, PDF is likely scanned — use OCR
  if (lines.length === 0) {
    console.log("No digital text found, falling back to OCR...");
    if (onProgress) onProgress("Scanning image with OCR...");
    lines = await extractWithOCR(pdf);
  }

  const fullText = lines.join("\n");

  console.log("PDF extracted lines:", lines);
  console.log("PDF extracted text (first 3000 chars):", fullText.substring(0, 3000));

  const cbc = extractCBCValues(lines, fullText);
  const patient = extractPatientInfo(fullText);

  console.log("Extracted CBC:", cbc);
  console.log("Extracted patient:", patient);

  return { cbc, patient };
}

/**
 * Extract text from a digital (non-scanned) PDF using pdfjs.
 */
async function extractDigitalText(pdf) {
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

      let found = false;
      for (const group of yGroups) {
        if (Math.abs(group.y - y) <= 3) {
          group.items.push({ x, str: item.str });
          group.y = (group.y + y) / 2;
          found = true;
          break;
        }
      }
      if (!found) {
        yGroups.push({ y, items: [{ x, str: item.str }] });
      }
    }

    yGroups.sort((a, b) => b.y - a.y);
    for (const group of yGroups) {
      group.items.sort((a, b) => a.x - b.x);
      const lineText = group.items.map((it) => it.str).join(" ");
      if (lineText.trim()) lines.push(lineText.trim());
    }
  }
  return lines;
}

/**
 * Render PDF pages to canvas and run Tesseract OCR.
 * Used as fallback for scanned/image-based PDFs.
 */
async function extractWithOCR(pdf) {
  const allLines = [];

  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    // Render at 2x scale for better OCR accuracy
    const scale = 2.0;
    const viewport = page.getViewport({ scale });

    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext("2d");

    await page.render({ canvasContext: ctx, viewport }).promise;

    // Run OCR on the rendered canvas
    const { data } = await Tesseract.recognize(canvas, "eng", {
      logger: (m) => {
        if (m.status === "recognizing text") {
          console.log(`OCR page ${i}: ${Math.round((m.progress || 0) * 100)}%`);
        }
      },
    });

    // Split OCR text into lines
    const ocrLines = data.text
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0);

    allLines.push(...ocrLines);
    console.log(`OCR page ${i}: ${ocrLines.length} lines extracted`);
  }

  return allLines;
}

/**
 * Given a line that matches a CBC label, extract the result value.
 * Looks for the first number AFTER the label text.
 */
function extractValueFromLine(line, labelPattern) {
  const labelMatch = line.match(labelPattern);
  if (!labelMatch) return undefined;

  const labelEnd = labelMatch.index + labelMatch[0].length;
  const afterLabel = line.substring(labelEnd);

  const numbers = afterLabel.match(/\d+\.?\d*/g);
  if (!numbers || numbers.length === 0) return undefined;

  const val = parseFloat(numbers[0]);
  if (!isNaN(val) && val > 0) return val;

  return undefined;
}

/**
 * Try to normalize a value into the expected clinical range,
 * applying unit conversions if needed.
 */
function normalizeValue(val, range) {
  if (val >= range[0] && val <= range[1]) return val;
  // OCR may drop decimal point: 445 → 44.5, 954 → 95.4
  if (val / 10 >= range[0] && val / 10 <= range[1]) {
    return val / 10;
  }
  // WBC: 8500 → 8.5 (×10³/µL)
  if (range[1] <= 50 && val > 100 && val / 1000 >= range[0] && val / 1000 <= range[1]) {
    return val / 1000;
  }
  // PLT: 250000 → 250 (×10³/µL)
  if (range[1] <= 1000 && val > 10000 && val / 1000 >= range[0] && val / 1000 <= range[1]) {
    return Math.round(val / 1000);
  }
  return undefined;
}

/**
 * Search lines for a label and extract the result value.
 */
function findValueInLines(lines, labelPatterns, range) {
  for (const line of lines) {
    for (const pattern of labelPatterns) {
      if (pattern.test(line)) {
        pattern.lastIndex = 0;
        const val = extractValueFromLine(line, pattern);
        if (val !== undefined) {
          const normalized = normalizeValue(val, range);
          if (normalized !== undefined) return normalized;
        }
      }
    }
  }
  return undefined;
}

// CBC parameter definitions with label patterns and clinical ranges
// Note: patterns avoid trailing \b after optional groups to match plurals (e.g. "Platelets")
// MCHC must come before MCH so MCHC lines aren't claimed by MCH
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
      /\bP[I1l][O0]N\b/i, // OCR garbles P.C.V → PION/P1ON
    ],
    range: [15, 65],
  },
  {
    key: "mcv",
    patterns: [
      /\bMCV\b/i,
      /\bM\s*\.?\s*C\s*\.?\s*V\s*\.?/i,
      /\bMC[:\s.]*V/i, // OCR garbles M.C.V. → MC: Vi:
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

  // Strategy 2: If line-based missed values, try adjacent lines and looser matching
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

        // Try all numbers on the line
        const nums = line.match(/\d+\.?\d*/g);
        if (nums) {
          for (const n of nums) {
            const v = parseFloat(n);
            const normalized = normalizeValue(v, range);
            if (normalized !== undefined) {
              cbc[key] = normalized;
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
            const normalized = normalizeValue(v, range);
            if (normalized !== undefined) {
              cbc[key] = normalized;
              break;
            }
          }
        }
      }
    }
  }

  // Strategy 3: Flat text regex extraction
  if (Object.keys(cbc).length < 8) {
    for (const { key, patterns, range } of CBC_MAPPINGS) {
      if (cbc[key] !== undefined) continue;
      for (const pattern of patterns) {
        const source = pattern.source;
        const regex = new RegExp(source + "[^\\d]*?(\\d+\\.?\\d*)", "i");
        const match = fullText.match(regex);
        if (match) {
          const val = parseFloat(match[1]);
          if (!isNaN(val) && val > 0) {
            const normalized = normalizeValue(val, range);
            if (normalized !== undefined) {
              cbc[key] = normalized;
              break;
            }
          }
        }
      }
    }
  }

  // Strategy 4: Section-based extraction for "Blood Indices"
  // OCR often garbles labels in this section (e.g. P.C.V → PION)
  // Expected order after "Blood Indices": PCV, MCV, MCH, MCHC, RDW
  const BLOOD_INDICES_ORDER = ["hct", "mcv", "mch", "mchc", "rdw"];
  const sectionIdx = lines.findIndex((l) => /blood\s*indic/i.test(l));
  if (sectionIdx >= 0) {
    let orderPos = 0;
    for (let i = sectionIdx + 1; i < lines.length && orderPos < BLOOD_INDICES_ORDER.length; i++) {
      const line = lines[i];
      // Skip lines that are section headers or have no numbers
      const nums = line.match(/\d+\.?\d*/g);
      if (!nums || /^(blood|differential|complete|test\s*name|result)/i.test(line)) continue;

      const key = BLOOD_INDICES_ORDER[orderPos];
      if (cbc[key] === undefined) {
        const mapping = CBC_MAPPINGS.find((m) => m.key === key);
        if (mapping) {
          for (const n of nums) {
            const v = parseFloat(n);
            const normalized = normalizeValue(v, mapping.range);
            if (normalized !== undefined) {
              cbc[key] = normalized;
              console.log(`Section-based: ${key} = ${normalized} from line: "${line}"`);
              break;
            }
          }
        }
      }
      orderPos++;
    }
  }

  return cbc;
}

function extractPatientInfo(text) {
  const patient = {};

  // Patient Name — terminators stop the lazy capture
  const NAME_TERMINATORS = /(?:\s{2,}|\n|Age|Sex|Gender|Patient\s*ID|DOB|Date|Ref\b|Reg\b|Sample|Lab\b|Barcode|Accession|Report|Bill|UHID|MRN)/i;
  const namePatterns = [
    new RegExp("Patient\\s*(?:'s\\s*)?(?:Name|name)\\s*[:\\-]\\s*([A-Za-z\\s.,']+?)" + NAME_TERMINATORS.source, "i"),
    new RegExp("Name\\s+of\\s+(?:the\\s+)?Patient\\s*[:\\-]\\s*([A-Za-z\\s.,']+?)" + NAME_TERMINATORS.source, "i"),
    new RegExp("(?:Client|Pt|Pat)\\.?\\s*Name\\s*[:\\-]\\s*([A-Za-z\\s.,']+?)" + NAME_TERMINATORS.source, "i"),
    new RegExp("Name\\s*[:\\-]\\s*(?:Mr\\.?|Mrs\\.?|Ms\\.?|Dr\\.?|Master|Baby)?\\s*([A-Za-z\\s.,']+?)" + NAME_TERMINATORS.source, "i"),
    new RegExp("Name\\s*[:\\-]\\s*([A-Za-z\\s.,']+?)" + NAME_TERMINATORS.source, "i"),
  ];
  for (const regex of namePatterns) {
    const match = text.match(regex);
    if (match && match[1].trim().length > 1) {
      let name = match[1].trim();
      name = name.replace(/\s+(Age|Sex|Gender|DOB|Date|Ref|Reg|Sample|Lab).*$/i, "").trim();
      if (name.length > 1 && name.length < 80) {
        patient.name = name;
        break;
      }
    }
  }

  // Age & Sex (often combined: "Age/Sex: 34 Years/Male")
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

  // Patient ID
  const idPatterns = [
    /(?:Patient\s*ID|MRN|Reg\.?\s*ID|Reg(?:istration)?\.?\s*No\.?|UHID|Lab\s*(?:No\.?|ID)|Sample\s*(?:No\.?|ID)|Barcode\s*(?:No\.?)?|Accession\s*(?:No\.?)?|Bill\s*No\.?|SID|Report\s*(?:No\.?|ID)|OPD\s*No\.?|IPD\s*No\.?|Visit\s*(?:No\.?|ID))\s*[:\-#]?\s*([A-Za-z0-9\-/]+)/i,
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

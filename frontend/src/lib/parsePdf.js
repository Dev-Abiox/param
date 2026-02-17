import * as pdfjsLib from "pdfjs-dist/legacy/build/pdf";
import pdfjsWorker from "pdfjs-dist/legacy/build/pdf.worker.entry";
import Tesseract from "tesseract.js";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

/**
 * Extract CBC values and patient info from a lab report PDF.
 * Uses pdfjs for digital PDFs, falls back to Tesseract OCR for scanned PDFs.
 */
export async function parsePdf(file, onProgress) {
  const arrayBuffer = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;

  // Try digital text extraction first
  let lines = await extractDigitalText(pdf);
  let isOCR = false;

  // If no text found, PDF is likely scanned — use OCR
  if (lines.length === 0) {
    console.log("No digital text found, falling back to OCR...");
    if (onProgress) onProgress("Scanning image with OCR (this may take a few seconds)...");
    lines = await extractWithOCR(pdf);
    isOCR = true;
  }

  const fullText = lines.join("\n");

  console.log("PDF extracted lines:", lines);
  console.log("PDF extracted text (first 3000 chars):", fullText.substring(0, 3000));

  const cbc = extractCBCValues(lines, fullText, isOCR);
  const patient = extractPatientInfo(lines, fullText);

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
 * Uses 3x scale and grayscale conversion for better accuracy.
 */
async function extractWithOCR(pdf) {
  const allLines = [];

  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const scale = 3.0; // Higher scale = better OCR accuracy
    const viewport = page.getViewport({ scale });

    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext("2d");

    // White background
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    await page.render({ canvasContext: ctx, viewport }).promise;

    // Convert to grayscale for better OCR
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const data = imageData.data;
    for (let j = 0; j < data.length; j += 4) {
      const gray = 0.299 * data[j] + 0.587 * data[j + 1] + 0.114 * data[j + 2];
      data[j] = data[j + 1] = data[j + 2] = gray;
    }
    ctx.putImageData(imageData, 0, 0);

    const { data: ocrData } = await Tesseract.recognize(canvas, "eng", {
      logger: (m) => {
        if (m.status === "recognizing text") {
          console.log(`OCR page ${i}: ${Math.round((m.progress || 0) * 100)}%`);
        }
      },
    });

    const ocrLines = ocrData.text
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0);

    allLines.push(...ocrLines);
    console.log(`OCR page ${i}: ${ocrLines.length} lines extracted`);
  }

  return allLines;
}

// ─── Value extraction helpers ───

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
 * Normalize value into expected clinical range with unit conversions.
 * isOCR flag enables more aggressive normalization (decimal recovery).
 */
function normalizeValue(val, range, isOCR) {
  if (val >= range[0] && val <= range[1]) return val;

  // OCR may drop decimal point: 445 → 44.5, 954 → 95.4
  // Only apply for OCR text, and only when val is clearly too large
  if (isOCR && val > range[1] && val / 10 >= range[0] && val / 10 <= range[1]) {
    return Math.round((val / 10) * 100) / 100; // Round to 2 decimals
  }

  // WBC: 6100 → 6.1 (×10³/µL)
  if (range[1] <= 50 && val > 100 && val / 1000 >= range[0] && val / 1000 <= range[1]) {
    return Math.round((val / 1000) * 10) / 10;
  }

  // PLT: 340000 → 340 (×10³/µL)
  if (range[1] <= 1000 && val > 10000 && val / 1000 >= range[0] && val / 1000 <= range[1]) {
    return Math.round(val / 1000);
  }

  return undefined;
}

function findValueInLines(lines, labelPatterns, range, isOCR) {
  for (const line of lines) {
    for (const pattern of labelPatterns) {
      if (pattern.test(line)) {
        pattern.lastIndex = 0;
        const val = extractValueFromLine(line, pattern);
        if (val !== undefined) {
          const normalized = normalizeValue(val, range, isOCR);
          if (normalized !== undefined) return normalized;
        }
      }
    }
  }
  return undefined;
}

// ─── CBC mappings ───
// MCHC MUST be before MCH (MCH has negative lookahead for C)

const CBC_MAPPINGS = [
  {
    key: "hb",
    patterns: [/\b(?:Haemoglobin|Hemoglobin|Hb|HGB)\b/i],
    range: [3, 25],
  },
  {
    key: "rbc",
    patterns: [
      /\b(?:Red\s*Blood\s*Cell|RBC|Erythrocyte)s?\s*(?:Count)?/i,
      /\bTotal\s*(?:RBC|R\s*\.?\s*B\s*\.?\s*C|Red\s*Blood|Erythrocyte)/i,
      /\bR\s*\.?\s*B\s*\.?\s*C\s*\.?\b/i,
    ],
    range: [1, 10],
  },
  {
    key: "wbc",
    patterns: [
      /\b(?:White\s*Blood\s*Cell|WBC|Leucocyte|Leukocyte)s?\s*(?:Count)?/i,
      /\bTotal\s*(?:WBC|W\s*\.?\s*B\s*\.?\s*C|White\s*Blood|Leu[ck]ocyte)\s*(?:Count)?/i,
      /\bW\s*\.?\s*B\s*\.?\s*C\s*\.?\b/i,
      /\bTLC\b/i,
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

// ─── CBC extraction ───

function extractCBCValues(lines, fullText, isOCR) {
  const cbc = {};

  // Strategy 1: Line-based pattern matching
  for (const { key, patterns, range } of CBC_MAPPINGS) {
    const val = findValueInLines(lines, patterns, range, isOCR);
    if (val !== undefined) {
      cbc[key] = val;
    }
  }

  // Strategy 2: Adjacent lines (label on one line, value on next)
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
          const normalized = normalizeValue(v, range, isOCR);
          if (normalized !== undefined) {
            cbc[key] = normalized;
            break;
          }
        }
      }
      if (cbc[key] !== undefined) break;

      // Check next line
      if (i + 1 < lines.length) {
        const nextNums = lines[i + 1].match(/^\s*(\d+\.?\d*)/);
        if (nextNums) {
          const v = parseFloat(nextNums[1]);
          const normalized = normalizeValue(v, range, isOCR);
          if (normalized !== undefined) {
            cbc[key] = normalized;
            break;
          }
        }
      }
    }
  }

  // Strategy 3: Section-based extraction
  // Uses known section order — most reliable for OCR where labels are garbled
  // Blood Counts: Hb, RBC, WBC, PLT
  // Differential: Neutrophils, Lymphocytes
  // Blood Indices: PCV/HCT, MCV, MCH, MCHC, RDW
  const SECTIONS = [
    { header: /blood\s*count/i, order: ["hb", "rbc", "wbc", "plt"] },
    { header: /differential/i, order: ["neu_pct", "lym_pct"] },
    { header: /blood\s*indic/i, order: ["hct", "mcv", "mch", "mchc", "rdw"] },
  ];

  for (const section of SECTIONS) {
    const sectionIdx = lines.findIndex((l) => section.header.test(l));
    if (sectionIdx < 0) continue;

    let orderPos = 0;
    for (let i = sectionIdx + 1; i < lines.length && orderPos < section.order.length; i++) {
      const line = lines[i];
      // Stop at next section header
      if (/^(blood|differential|complete|test\s*name|haematological|hematological)/i.test(line)) break;

      const nums = line.match(/\d+\.?\d*/g);
      if (!nums) continue;

      const key = section.order[orderPos];
      if (cbc[key] === undefined) {
        const mapping = CBC_MAPPINGS.find((m) => m.key === key);
        if (mapping) {
          for (const n of nums) {
            const v = parseFloat(n);
            const normalized = normalizeValue(v, mapping.range, isOCR);
            if (normalized !== undefined) {
              cbc[key] = normalized;
              console.log(`Section "${section.header.source}": ${key} = ${normalized} from: "${line}"`);
              break;
            }
          }
        }
      }
      orderPos++;
    }
  }

  // Strategy 4: Flat text regex (last resort)
  if (Object.keys(cbc).length < 8) {
    for (const { key, patterns, range } of CBC_MAPPINGS) {
      if (cbc[key] !== undefined) continue;
      for (const pattern of patterns) {
        const regex = new RegExp(pattern.source + "[^\\d]*?(\\d+\\.?\\d*)", "i");
        const match = fullText.match(regex);
        if (match) {
          const val = parseFloat(match[1]);
          if (!isNaN(val) && val > 0) {
            const normalized = normalizeValue(val, range, isOCR);
            if (normalized !== undefined) {
              cbc[key] = normalized;
              break;
            }
          }
        }
      }
    }
  }

  return cbc;
}

// ─── Patient info extraction ───
// Uses line-by-line search for better OCR compatibility

function extractPatientInfo(lines, fullText) {
  const patient = {};

  // Search each line for patient details
  for (const line of lines) {
    // Patient Name
    if (!patient.name) {
      const nameMatch = line.match(
        /(?:Patient(?:'s)?|Pat\.?)\s*(?:Name|name)\s*[:\-]\s*(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Master|Baby)?\s*([A-Za-z][A-Za-z\s.,']{1,60})/i
      );
      if (nameMatch) {
        let name = nameMatch[1].trim();
        // Trim at common suffixes that appear on the same line
        name = name.replace(/\s+(Age|Sex|Gender|DOB|Date|Ref|Reg|Sample|Lab|ID|Accession|Report|Bill|UHID|MRN|Referred).*$/i, "").trim();
        if (name.length > 1 && name.length < 80) {
          patient.name = name;
        }
      }
    }

    // Name: ... (simpler fallback)
    if (!patient.name) {
      const nameMatch2 = line.match(
        /\bName\s*[:\-]\s*(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Master|Baby)?\s*([A-Za-z][A-Za-z\s.,']{1,60})/i
      );
      if (nameMatch2) {
        let name = nameMatch2[1].trim();
        name = name.replace(/\s+(Age|Sex|Gender|DOB|Date|Ref|Reg|Sample|Lab|ID|Accession|Report|Referred).*$/i, "").trim();
        if (name.length > 1 && name.length < 80 && !/^(Test|Result|Unit|Reference|Biological|Blood|Complete)/i.test(name)) {
          patient.name = name;
        }
      }
    }

    // Age/Sex combined: "Age/Sex : 34 Years/Male" or "Age/Sex: 34 Y/M"
    if (!patient.age) {
      const ageSexMatch = line.match(
        /Age\s*[/&]\s*(?:Sex|Gender)\s*[:\-]?\s*(\d{1,3})\s*(?:yrs?|years?|Y|Yrs)?\.?\s*[/\\|,\s]+\s*(M(?:ale)?|F(?:emale)?)/i
      );
      if (ageSexMatch) {
        const age = parseInt(ageSexMatch[1], 10);
        if (age > 0 && age < 150) {
          patient.age = age;
          patient.sex = ageSexMatch[2].charAt(0).toUpperCase() === "M" ? "M" : "F";
        }
      }
    }

    // Age alone: "Age : 34 Years" or "Age: 34"
    if (!patient.age) {
      const ageMatch = line.match(/\bAge\s*[:\-]\s*(\d{1,3})\s*(?:yrs?|years?|Y|Yrs)?/i);
      if (ageMatch) {
        const age = parseInt(ageMatch[1], 10);
        if (age > 0 && age < 150) patient.age = age;
      }
    }

    // "34 Years/Male" pattern
    if (!patient.age) {
      const ageMatch2 = line.match(/(\d{1,3})\s*(?:yrs?|years?)\s*[/\\|,\s]+\s*(M(?:ale)?|F(?:emale)?)/i);
      if (ageMatch2) {
        const age = parseInt(ageMatch2[1], 10);
        if (age > 0 && age < 150) {
          patient.age = age;
          if (!patient.sex) patient.sex = ageMatch2[2].charAt(0).toUpperCase() === "M" ? "M" : "F";
        }
      }
    }

    // Sex alone
    if (!patient.sex) {
      const sexMatch = line.match(/(?:Sex|Gender)\s*[:\-]\s*(Male|Female|M|F)\b/i);
      if (sexMatch) {
        patient.sex = sexMatch[1].charAt(0).toUpperCase() === "M" ? "M" : "F";
      }
    }

    // Patient ID / Registration ID / Reg. ID
    if (!patient.id) {
      const idMatch = line.match(
        /(?:Patient\s*ID|Reg\.?\s*ID|Reg(?:istration)?\.?\s*No\.?|MRN|UHID|Lab\s*(?:No\.?|ID)|Sample\s*(?:No\.?|ID)|Barcode\s*No\.?|Accession\s*No\.?|Bill\s*No\.?|Report\s*(?:No\.?|ID)|OPD\s*No\.?|IPD\s*No\.?|SID)\s*[:\-#]?\s*([A-Za-z0-9][\w\-/]*)/i
      );
      if (idMatch && idMatch[1].trim().length > 1) {
        patient.id = idMatch[1].trim();
      }
    }
  }

  // Fallback: search fullText for Male/Female if sex not found
  if (!patient.sex) {
    const sexMatch = fullText.match(/\b(Male|Female)\b/i);
    if (sexMatch) patient.sex = sexMatch[1].charAt(0).toUpperCase() === "M" ? "M" : "F";
  }

  return patient;
}

import * as pdfjsLib from "pdfjs-dist";
import Tesseract from "tesseract.js";

pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.mjs`;

/**
 * Extract CBC values and patient info from a lab report PDF.
 * Uses pdfjs for digital PDFs, falls back to Tesseract OCR for scanned PDFs.
 */
export async function parsePdf(file, onProgress) {
  const arrayBuffer = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;

  let lines = await extractDigitalText(pdf);
  let isOCR = false;

  if (lines.length === 0) {
    // Digital text extraction failed — fall back to OCR
    if (onProgress) onProgress("Scanning image with OCR...");
    lines = await extractWithOCR(pdf);
    isOCR = true;
  }

  const fullText = lines.join("\n");

  const cbc = extractCBCValues(lines, fullText, isOCR);
  const patient = extractPatientInfo(lines, fullText);

  return { cbc, patient };
}

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

async function extractWithOCR(pdf) {
  const allLines = [];

  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const scale = 2.5;
    const viewport = page.getViewport({ scale });

    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext("2d");

    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    await page.render({ canvasContext: ctx, viewport }).promise;

    // Increase contrast for better OCR
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const d = imageData.data;
    for (let j = 0; j < d.length; j += 4) {
      const gray = 0.299 * d[j] + 0.587 * d[j + 1] + 0.114 * d[j + 2];
      // Apply threshold for cleaner binary image
      const val = gray < 140 ? 0 : 255;
      d[j] = d[j + 1] = d[j + 2] = val;
    }
    ctx.putImageData(imageData, 0, 0);

    const { data: ocrData } = await Tesseract.recognize(canvas, "eng", {
      logger: (m) => {
        if (m.status === "recognizing text") {
          // OCR progress tracked internally
        }
      },
    });

    const ocrLines = ocrData.text
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0);

    allLines.push(...ocrLines);
    // OCR extraction complete for page
  }

  return allLines;
}

// ─── Value helpers ───

function extractValueFromLine(line, labelPattern) {
  const m = line.match(labelPattern);
  if (!m) return undefined;
  const after = line.substring(m.index + m[0].length);
  const nums = after.match(/\d+\.?\d*/g);
  if (!nums) return undefined;
  const val = parseFloat(nums[0]);
  return (!isNaN(val) && val > 0) ? val : undefined;
}

function normalizeValue(val, range, isOCR) {
  if (val >= range[0] && val <= range[1]) return val;
  // OCR decimal recovery: 445 → 44.5 (only when clearly out of range)
  if (isOCR && val > range[1] && val < range[1] * 100) {
    if (val / 10 >= range[0] && val / 10 <= range[1]) {
      return Math.round((val / 10) * 100) / 100;
    }
  }
  // Unit conversions (always applied)
  if (val > 100 && val / 1000 >= range[0] && val / 1000 <= range[1]) {
    return Math.round((val / 1000) * 10) / 10;
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
          const n = normalizeValue(val, range, isOCR);
          if (n !== undefined) return n;
        }
      }
    }
  }
  return undefined;
}

// ─── CBC mappings ───

const CBC_MAPPINGS = [
  {
    key: "hb",
    patterns: [/\b(?:Haemoglobin|Hemoglobin|Hb|HGB|Haemo\s*globin|Hemo\s*globin)\b/i],
    range: [3, 25],
  },
  {
    key: "rbc",
    patterns: [
      /\b(?:Red\s*Blood\s*Cell|Erythrocyte)s?\s*(?:Count)?/i,
      /\bTotal\s*R\s*\.?\s*B\s*\.?\s*C/i,
      /\bRBC\s*(?:Count)?/i,
      /\bR\s*\.?\s*B\s*\.?\s*C\s*\.?\s*(?:Count)?/i,
    ],
    range: [1, 10],
  },
  {
    key: "wbc",
    patterns: [
      /\b(?:White\s*Blood\s*Cell|Leucocyte|Leukocyte)s?\s*(?:Count)?/i,
      /\bTotal\s*W\s*\.?\s*B\s*\.?\s*C/i,
      /\bWBC\s*(?:Count)?/i,
      /\bW\s*\.?\s*B\s*\.?\s*C\s*\.?\s*(?:Count)?/i,
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
      /\bP\s*\.?\s*C\s*\.?\s*V\b/i,
      /\bPacked\s*Cell\s*Volume/i,
    ],
    range: [15, 65],
  },
  {
    key: "mcv",
    patterns: [
      /\bMCV\b/i,
      /\bM\s*\.\s*C\s*\.\s*V/i,
      /\bMean\s*(?:Corpuscular|Cell)\s*Volume/i,
    ],
    range: [50, 150],
  },
  {
    key: "mchc",
    patterns: [
      /\bMCHC\b/i,
      /\bM\s*\.?\s*C\s*\.?\s*H\s*\.?\s*C\b/i,
      /\bMean\s*(?:Corpuscular|Cell)\s*Hemo?globin\s*Conc/i,
    ],
    range: [25, 40],
  },
  {
    key: "mch",
    patterns: [
      /\bMCH\b(?!\s*C)/i,
      /\bM\s*\.\s*C\s*\.\s*H\b(?!\s*\.?\s*C)/i,
      /\bMean\s*(?:Corpuscular|Cell)\s*Hemo?globin\b(?!\s*Conc)/i,
    ],
    range: [15, 45],
  },
  {
    key: "rdw",
    patterns: [
      /\bRDW[\s\-]*(?:CV|SD)?/i,
      /\bR\s*\.?\s*D\s*\.?\s*W\b/i,
      /\bRed\s*(?:Cell\s*)?Distribution\s*Width/i,
    ],
    range: [8, 30],
  },
  {
    key: "neu_pct",
    patterns: [
      /\bNeutrophils?\b/i,
      /\bNEUT(?:RO)?S?\b/i,
      /\bSegmented\s*Neutrophil/i,
      /\bPolymorphs?\b/i,
    ],
    range: [5, 95],
  },
  {
    key: "lym_pct",
    patterns: [
      /\bLymphocytes?\b/i,
      /\bLYMPH?S?\b/i,
    ],
    range: [2, 80],
  },
];

// ─── CBC extraction ───

function extractCBCValues(lines, fullText, isOCR) {
  const cbc = {};

  // Strategy 1: Label pattern matching (line by line)
  for (const { key, patterns, range } of CBC_MAPPINGS) {
    const val = findValueInLines(lines, patterns, range, isOCR);
    if (val !== undefined) {
      cbc[key] = val;
      // S1 matched
    }
  }

  // Strategy 2: Adjacent line fallback
  for (const { key, patterns, range } of CBC_MAPPINGS) {
    if (cbc[key] !== undefined) continue;
    for (let i = 0; i < lines.length; i++) {
      let matched = false;
      for (const p of patterns) {
        if (p.test(lines[i])) { p.lastIndex = 0; matched = true; break; }
      }
      if (!matched) continue;

      const nums = lines[i].match(/\d+\.?\d*/g);
      if (nums) {
        for (const n of nums) {
          const v = normalizeValue(parseFloat(n), range, isOCR);
          if (v !== undefined) { cbc[key] = v; break; }
        }
      }
      if (cbc[key] !== undefined) break;

      if (i + 1 < lines.length) {
        const nxt = lines[i + 1].match(/^\s*(\d+\.?\d*)/);
        if (nxt) {
          const v = normalizeValue(parseFloat(nxt[1]), range, isOCR);
          if (v !== undefined) { cbc[key] = v; break; }
        }
      }
    }
  }

  // Strategy 3: Section-based extraction (most reliable for OCR)
  // Uses known section order when labels are garbled
  const SECTIONS = [
    { headers: [/blood\s*count/i, /haemo/i], order: ["hb", "rbc", "wbc", "plt"] },
    { headers: [/differential/i], order: ["neu_pct", "lym_pct"] },
    { headers: [/blood\s*indic/i, /indice/i, /P\s*\.?\s*C\s*\.?\s*V/i], order: ["hct", "mcv", "mch", "mchc", "rdw"] },
  ];

  for (const section of SECTIONS) {
    let sectionIdx = -1;
    for (const h of section.headers) {
      sectionIdx = lines.findIndex((l) => h.test(l));
      if (sectionIdx >= 0) break;
    }
    if (sectionIdx < 0) continue;
    // S3 section found

    let orderPos = 0;
    for (let i = sectionIdx + 1; i < lines.length && orderPos < section.order.length; i++) {
      const line = lines[i];
      // Stop at next section
      if (/^(blood|differential|complete|test\s*name|haematological|hematological|platelets\s+platelets)/i.test(line)) break;

      const nums = line.match(/\d+\.?\d*/g);
      if (!nums) continue;

      const key = section.order[orderPos];
      if (cbc[key] === undefined) {
        const mapping = CBC_MAPPINGS.find((m) => m.key === key);
        if (mapping) {
          for (const n of nums) {
            const v = normalizeValue(parseFloat(n), mapping.range, isOCR);
            if (v !== undefined) {
              cbc[key] = v;
              // S3 matched
              break;
            }
          }
        }
      }
      orderPos++;
    }
  }

  // Strategy 4: Flat text regex (last resort)
  for (const { key, patterns, range } of CBC_MAPPINGS) {
    if (cbc[key] !== undefined) continue;
    for (const pattern of patterns) {
      const regex = new RegExp(pattern.source + "[^\\d]*?(\\d+\\.?\\d*)", "i");
      const m = fullText.match(regex);
      if (m) {
        const v = normalizeValue(parseFloat(m[1]), range, isOCR);
        if (v !== undefined) {
          cbc[key] = v;
          // S4 matched
          break;
        }
      }
    }
  }

  return cbc;
}

// ─── Patient info extraction ───

function extractPatientInfo(lines, fullText) {
  const patient = {};

  for (const line of lines) {
    // Patient Name — very flexible OCR-tolerant pattern
    // Handles: Patient's Name, Patient name, Patient' s name, Patients name, Pat. Name
    if (!patient.name) {
      const m = line.match(
        /(?:Patient|Pat)[''`]?s?\s*(?:Name|name|NAME)\s*[:;\-.\s]\s*(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Master|Baby|Smt\.?)?\s*([A-Za-z][A-Za-z\s.,']{1,60})/i
      );
      if (m) {
        let name = m[1].trim();
        name = name.replace(/\s+(Age|Sex|Gender|DOB|Date|Ref|Reg|Sample|Lab|ID|Acc|Report|Bill|UHID|MRN|Referred|Barcode).*$/i, "").trim();
        if (name.length > 1 && name.length < 80) {
          patient.name = name;
          // Patient name extracted
        }
      }
    }

    // Fallback: "Name : Xyz" (but not "Test Name")
    if (!patient.name) {
      const m = line.match(
        /(?<!\bTest\s)\bName\s*[:;\-]\s*(?:Mr\.?|Mrs\.?|Ms\.?|Dr\.?|Master|Baby|Smt\.?)?\s*([A-Za-z][A-Za-z\s.,']{1,60})/i
      );
      if (m) {
        let name = m[1].trim();
        name = name.replace(/\s+(Age|Sex|Gender|DOB|Date|Ref|Reg|Sample|Lab|ID|Report|Referred|Result|Unit).*$/i, "").trim();
        if (name.length > 1 && name.length < 80 && !/^(Test|Result|Unit|Reference|Biological|Blood|Complete|Sample)/i.test(name)) {
          patient.name = name;
          // Patient name extracted (fallback)
        }
      }
    }

    // Age/Sex combined — very flexible separator handling
    if (!patient.age) {
      const m = line.match(
        /Age\s*[/&\\]\s*(?:Sex|Gender)\s*[:;\-.\s]\s*(\d{1,3})\s*(?:yrs?|years?|Y|Yrs)?\.?\s*[/\\|,\s]+\s*(M(?:ale)?|F(?:emale)?)/i
      );
      if (m) {
        const age = parseInt(m[1], 10);
        if (age > 0 && age < 150) {
          patient.age = age;
          patient.sex = m[2].charAt(0).toUpperCase() === "M" ? "M" : "F";
          // Age/Sex extracted
        }
      }
    }

    // "XX Years/Male" pattern (without Age label)
    if (!patient.age) {
      const m = line.match(/(\d{1,3})\s*(?:yrs?|years?)\s*[/\\|,\s]+\s*(M(?:ale)?|F(?:emale)?)/i);
      if (m) {
        const age = parseInt(m[1], 10);
        if (age > 0 && age < 150) {
          patient.age = age;
          if (!patient.sex) patient.sex = m[2].charAt(0).toUpperCase() === "M" ? "M" : "F";
        }
      }
    }

    // Age alone
    if (!patient.age) {
      const m = line.match(/\bAge\s*[:;\-.\s]\s*(\d{1,3})\s*(?:yrs?|years?|Y|Yrs)?/i);
      if (m) {
        const age = parseInt(m[1], 10);
        if (age > 0 && age < 150) patient.age = age;
      }
    }

    // Sex alone
    if (!patient.sex) {
      const m = line.match(/(?:Sex|Gender)\s*[:;\-.\s]\s*(Male|Female|M|F)\b/i);
      if (m) {
        patient.sex = m[1].charAt(0).toUpperCase() === "M" ? "M" : "F";
        // Sex extracted
      }
    }

    // Patient ID
    if (!patient.id) {
      const m = line.match(
        /(?:Patient\s*ID|Reg\.?\s*ID|Reg(?:istration)?\.?\s*No\.?|MRN|UHID|Lab\s*(?:No\.?|ID)|Sample\s*(?:No\.?|ID)|Barcode\s*No\.?|Accession|Bill\s*No\.?|Report\s*(?:No\.?|ID)|OPD\s*No\.?|IPD\s*No\.?|SID)\s*[:;\-#.\s]\s*([A-Za-z0-9][\w\-/]*)/i
      );
      if (m && m[1].trim().length > 1) {
        patient.id = m[1].trim();
        // Patient ID extracted
      }
    }
  }

  // Final fallback for sex
  if (!patient.sex) {
    const m = fullText.match(/\b(Male|Female)\b/i);
    if (m) patient.sex = m[1].charAt(0).toUpperCase() === "M" ? "M" : "F";
  }

  return patient;
}

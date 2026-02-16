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

    // Group text items by Y position to reconstruct lines
    const itemsByY = {};
    for (const item of content.items) {
      const y = Math.round(item.transform[5]); // Y coordinate
      if (!itemsByY[y]) itemsByY[y] = [];
      itemsByY[y].push({ x: item.transform[4], str: item.str });
    }

    // Sort by Y (descending = top to bottom) then X (left to right)
    const sortedYs = Object.keys(itemsByY).sort((a, b) => b - a);
    for (const y of sortedYs) {
      const lineItems = itemsByY[y].sort((a, b) => a.x - b.x);
      const lineText = lineItems.map((it) => it.str).join(" ");
      if (lineText.trim()) lines.push(lineText.trim());
    }
  }

  const fullText = lines.join("\n");

  // Debug: log extracted text to console for troubleshooting
  console.log("PDF extracted text (first 2000 chars):", fullText.substring(0, 2000));

  const cbc = extractCBCValues(lines, fullText);
  const patient = extractPatientInfo(fullText);

  return { cbc, patient };
}

/**
 * Search lines for a label and extract the first numeric value on that line.
 */
function findValueInLines(lines, labelPatterns) {
  for (const line of lines) {
    for (const pattern of labelPatterns) {
      if (pattern.test(line)) {
        // Find all numbers on this line
        const numbers = line.match(/\d+\.?\d*/g);
        if (numbers) {
          // Return the first reasonable number (skip very small ones like indices)
          for (const num of numbers) {
            const val = parseFloat(num);
            if (!isNaN(val) && val > 0) return val;
          }
        }
      }
    }
  }
  return undefined;
}

function extractCBCValues(lines, fullText) {
  const cbc = {};

  const mappings = [
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
        /\b(?:Red\s*Blood\s*Cell|RBC|Erythrocyte)\b/i,
        /\bRBC\s*Count\b/i,
        /\bTotal\s*RBC\b/i,
      ],
      range: [1, 10],
    },
    {
      key: "wbc",
      patterns: [
        /\b(?:White\s*Blood\s*Cell|WBC|Leucocyte|Leukocyte)\b/i,
        /\bWBC\s*Count\b/i,
        /\bTotal\s*WBC\b/i,
        /\bTotal\s*Leucocyte\s*Count\b/i,
        /\bTLC\b/i,
      ],
      range: [1, 50],
    },
    {
      key: "plt",
      patterns: [
        /\b(?:Platelet|PLT|Thrombocyte)\b/i,
        /\bPlatelet\s*Count\b/i,
      ],
      range: [10, 1000],
    },
    {
      key: "hct",
      patterns: [
        /\b(?:Hematocrit|Haematocrit|HCT|PCV)\b/i,
        /\bPacked\s*Cell\s*Volume\b/i,
      ],
      range: [15, 65],
    },
    {
      key: "mcv",
      patterns: [
        /\bMCV\b/i,
        /\bMean\s*Corpuscular\s*Volume\b/i,
      ],
      range: [50, 150],
    },
    {
      key: "mch",
      patterns: [
        /\bMCH\b(?!\s*C)/i,
        /\bMean\s*Corpuscular\s*Hemo?globin\b(?!\s*Conc)/i,
      ],
      range: [15, 45],
    },
    {
      key: "mchc",
      patterns: [
        /\bMCHC\b/i,
        /\bMean\s*Corpuscular\s*Hemo?globin\s*Conc/i,
      ],
      range: [25, 40],
    },
    {
      key: "rdw",
      patterns: [
        /\bRDW\b/i,
        /\bRed\s*(?:Cell\s*)?Distribution\s*Width\b/i,
      ],
      range: [8, 30],
    },
    {
      key: "neu_pct",
      patterns: [
        /\bNeutrophil/i,
        /\bNEUT?\b/i,
        /\bSegmented\b/i,
      ],
      range: [5, 95],
    },
    {
      key: "lym_pct",
      patterns: [
        /\bLymphocyte/i,
        /\bLYM(?:PH)?\b/i,
      ],
      range: [2, 80],
    },
  ];

  for (const { key, patterns, range } of mappings) {
    const val = findValueInLines(lines, patterns);
    if (val !== undefined && val >= range[0] && val <= range[1]) {
      cbc[key] = val;
    }
  }

  // Fallback: try flat text extraction if line-based didn't find enough
  if (Object.keys(cbc).length < 5) {
    for (const { key, patterns, range } of mappings) {
      if (cbc[key] !== undefined) continue; // already found
      for (const pattern of patterns) {
        const source = pattern.source;
        const regex = new RegExp(source + "[^\\d]*?(\\d+\\.?\\d*)", "i");
        const match = fullText.match(regex);
        if (match) {
          const val = parseFloat(match[1]);
          if (!isNaN(val) && val >= range[0] && val <= range[1]) {
            cbc[key] = val;
            break;
          }
        }
      }
    }
  }

  return cbc;
}

function extractPatientInfo(text) {
  const patient = {};

  // Patient Name
  const namePatterns = [
    /Patient\s*(?:'s\s*)?Name\s*[:\-]\s*([A-Za-z\s.,']+?)(?:\s{2,}|\n|Age|Sex|Gender|Patient\s*ID|DOB|Date|Ref)/i,
    /Name\s*[:\-]\s*([A-Za-z\s.,']+?)(?:\s{2,}|\n|Age|Sex|Gender|Patient\s*ID|DOB|Date)/i,
    /Pt\.?\s*Name\s*[:\-]\s*([A-Za-z\s.,']+?)(?:\s{2,}|\n|Age|Sex|Gender)/i,
  ];
  for (const regex of namePatterns) {
    const match = text.match(regex);
    if (match && match[1].trim().length > 1) {
      patient.name = match[1].trim();
      break;
    }
  }

  // Age
  const agePatterns = [
    /Age\s*[/&]\s*Sex\s*[:\-]\s*(\d{1,3})\s*(?:yrs?|years?|Y|Yrs)?\s*[/\\]\s*(M|F|Male|Female)/i,
    /Age\s*[:\-]\s*(\d{1,3})\s*(?:yrs?|years?|Y|Yrs)?/i,
    /(\d{1,3})\s*(?:yrs?|years?|Y)\s*[/\\]\s*(M|F|Male|Female)/i,
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
    /(?:Patient\s*ID|MRN|Reg(?:istration)?\.?\s*No|UHID|Lab\s*(?:No|ID)|Sample\s*(?:No|ID)|Barcode|Accession|Bill\s*No|SID)\s*[:\-#]\s*([A-Za-z0-9\-/]+)/i,
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

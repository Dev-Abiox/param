import * as pdfjsLib from "pdfjs-dist";

// Use the bundled worker
pdfjsLib.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.mjs`;

/**
 * Extract CBC values and patient info from a lab report PDF.
 * Returns { cbc: { hb, rbc, ... }, patient: { name, age, sex, id } }
 * Only includes fields that were successfully extracted.
 */
export async function parsePdf(file) {
  const arrayBuffer = await file.arrayBuffer();
  const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;

  // Extract text from all pages
  let fullText = "";
  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const content = await page.getTextContent();
    const pageText = content.items.map((item) => item.str).join(" ");
    fullText += pageText + "\n";
  }

  const cbc = extractCBCValues(fullText);
  const patient = extractPatientInfo(fullText);

  return { cbc, patient };
}

/**
 * Extract a numeric value near a label pattern.
 * Looks for patterns like "Hemoglobin 13.5" or "Hb: 13.5 g/dL"
 */
function extractValue(text, patterns) {
  for (const pattern of patterns) {
    const regex = new RegExp(
      pattern + "[:\\s]*([\\d]+\\.?[\\d]*)",
      "i"
    );
    const match = text.match(regex);
    if (match) {
      const val = parseFloat(match[1]);
      if (!isNaN(val)) return val;
    }
  }
  return undefined;
}

function extractCBCValues(text) {
  const cbc = {};

  const mappings = [
    {
      key: "hb",
      patterns: [
        "Haemoglobin|Hemoglobin|\\bHb\\b|\\bHGB\\b",
      ],
      range: [3, 25], // reasonable g/dL range
    },
    {
      key: "rbc",
      patterns: [
        "Red Blood Cell(?:s)?(?:\\s*Count)?|\\bRBC\\b(?:\\s*Count)?|Erythrocyte(?:s)?(?:\\s*Count)?",
      ],
      range: [1, 10], // x10^6/µL
    },
    {
      key: "wbc",
      patterns: [
        "White Blood Cell(?:s)?(?:\\s*Count)?|\\bWBC\\b(?:\\s*Count)?|Leucocyte(?:s)?(?:\\s*Count)?|Total\\s*WBC|Total\\s*Leucocyte",
      ],
      range: [1, 50], // x10^3/µL
    },
    {
      key: "plt",
      patterns: [
        "Platelet(?:s)?(?:\\s*Count)?|\\bPLT\\b(?:\\s*Count)?|Thrombocyte(?:s)?",
      ],
      range: [10, 1000], // x10^3/µL
    },
    {
      key: "hct",
      patterns: [
        "Hematocrit|Haematocrit|\\bHCT\\b|Packed\\s*Cell\\s*Volume|\\bPCV\\b",
      ],
      range: [15, 65], // %
    },
    {
      key: "mcv",
      patterns: [
        "Mean\\s*Corpuscular\\s*Volume|\\bMCV\\b",
      ],
      range: [50, 150], // fL
    },
    {
      key: "mch",
      patterns: [
        "Mean\\s*Corpuscular\\s*Hemo?globin(?!\\s*Conc)|\\bMCH\\b(?!C)",
      ],
      range: [15, 45], // pg
    },
    {
      key: "mchc",
      patterns: [
        "Mean\\s*Corpuscular\\s*Hemo?globin\\s*Conc(?:entration)?|\\bMCHC\\b",
      ],
      range: [25, 40], // g/dL
    },
    {
      key: "rdw",
      patterns: [
        "Red\\s*(?:Cell\\s*)?Distribution\\s*Width|\\bRDW\\b(?:[\\s-]*(?:CV|SD))?",
      ],
      range: [8, 30], // %
    },
    {
      key: "neu_pct",
      patterns: [
        "Neutrophil(?:s)?(?:\\s*%)?|\\bNEUT?\\b(?:\\s*%)?|Segmented\\s*Neutrophil",
      ],
      range: [5, 95], // %
    },
    {
      key: "lym_pct",
      patterns: [
        "Lymphocyte(?:s)?(?:\\s*%)?|\\bLYM(?:PH)?\\b(?:\\s*%)?",
      ],
      range: [2, 80], // %
    },
  ];

  for (const { key, patterns, range } of mappings) {
    const val = extractValue(text, patterns);
    if (val !== undefined && val >= range[0] && val <= range[1]) {
      cbc[key] = val;
    }
  }

  return cbc;
}

function extractPatientInfo(text) {
  const patient = {};

  // Patient Name
  const namePatterns = [
    /Patient\s*Name\s*[:\-]\s*([A-Za-z\s.]+?)(?:\s{2,}|\n|Age|Sex|Gender|Patient\s*ID|DOB|Date)/i,
    /Name\s*[:\-]\s*([A-Za-z\s.]+?)(?:\s{2,}|\n|Age|Sex|Gender|Patient\s*ID|DOB|Date)/i,
    /Pt\.?\s*Name\s*[:\-]\s*([A-Za-z\s.]+?)(?:\s{2,}|\n|Age|Sex|Gender)/i,
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
    /Age\s*[/&]\s*Sex\s*[:\-]\s*(\d{1,3})\s*(?:yrs?|years?|Y)?\s*[/\\]\s*(M|F|Male|Female)/i,
    /Age\s*[:\-]\s*(\d{1,3})\s*(?:yrs?|years?|Y)?/i,
  ];
  for (const regex of agePatterns) {
    const match = text.match(regex);
    if (match) {
      const age = parseInt(match[1], 10);
      if (age > 0 && age < 150) {
        patient.age = age;
        // Also extract sex from combined Age/Sex field
        if (match[2]) {
          patient.sex = match[2].charAt(0).toUpperCase() === "M" ? "M" : "F";
        }
        break;
      }
    }
  }

  // Sex (if not already extracted from Age/Sex)
  if (!patient.sex) {
    const sexPatterns = [
      /(?:Sex|Gender)\s*[:\-]\s*(Male|Female|M|F)/i,
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
    /(?:Patient\s*ID|MRN|Reg(?:istration)?\.?\s*No|UHID|Lab\s*(?:No|ID)|Sample\s*(?:No|ID)|Barcode|Accession)\s*[:\-#]\s*([A-Za-z0-9\-/]+)/i,
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

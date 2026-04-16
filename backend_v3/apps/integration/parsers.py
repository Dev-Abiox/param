"""
Inbound parsers — extract CBC fields from external LIS formats.

Each parser takes a raw payload (bytes or dict) and returns a normalized dict
with Clinomic CBC field names: Age, Sex, Hb, RBC, HCT, MCV, MCH, MCHC, RDW,
WBC, Platelets, Neutrophils, Lymphocytes, plus patient_id and (optionally)
lab_code, doctor_code.

If the integration endpoint has a field_mapping, it's applied AFTER format-
specific parsing to remap non-standard field names.
"""

import csv
import io
import json
import re

# Standard CBC fields the ML engine expects
CLINOMIC_CBC_FIELDS = {
    'Age', 'Sex', 'Hb', 'RBC', 'HCT', 'MCV', 'MCH', 'MCHC',
    'RDW', 'WBC', 'Platelets', 'Neutrophils', 'Lymphocytes',
}

# Common aliases used by Indian LIS vendors / analyzers.
# Applied as a fallback if the endpoint's custom field_mapping doesn't cover a field.
DEFAULT_ALIASES = {
    'HGB': 'Hb', 'Hemoglobin': 'Hb', 'hgb': 'Hb', 'hemoglobin': 'Hb',
    'RBC_COUNT': 'RBC', 'rbc_count': 'RBC', 'Red Blood Cells': 'RBC',
    'HCT_PCT': 'HCT', 'Hematocrit': 'HCT', 'hematocrit': 'HCT', 'PCV': 'HCT',
    'MCV_FL': 'MCV', 'mcv': 'MCV',
    'MCH_PG': 'MCH', 'mch': 'MCH',
    'MCHC_GDPL': 'MCHC', 'mchc': 'MCHC',
    'RDW_CV': 'RDW', 'RDW_PCT': 'RDW', 'rdw': 'RDW', 'RDW-CV': 'RDW',
    'WBC_COUNT': 'WBC', 'wbc': 'WBC', 'White Blood Cells': 'WBC', 'Leukocytes': 'WBC',
    'PLT': 'Platelets', 'PLT_COUNT': 'Platelets', 'plt': 'Platelets', 'Platelet Count': 'Platelets',
    'NEUT': 'Neutrophils', 'NEUT_PCT': 'Neutrophils', 'Neutrophil': 'Neutrophils', 'ANC': 'Neutrophils',
    'LYMPH': 'Lymphocytes', 'LYMPH_PCT': 'Lymphocytes', 'Lymphocyte': 'Lymphocytes',
    'AGE': 'Age', 'age': 'Age', 'PATIENT_AGE': 'Age',
    'SEX': 'Sex', 'sex': 'Sex', 'GENDER': 'Sex', 'gender': 'Sex',
    'PATIENT_ID': 'patient_id', 'PatientID': 'patient_id', 'MRN': 'patient_id',
    'patient_id': 'patient_id', 'patientId': 'patient_id',
    'LAB_CODE': 'lab_code', 'labCode': 'lab_code', 'lab_id': 'lab_code',
    'DOCTOR_CODE': 'doctor_code', 'doctorCode': 'doctor_code',
}


class ParseError(Exception):
    """Raised when inbound data cannot be parsed."""


def apply_field_mapping(raw: dict, custom_mapping: dict) -> dict:
    """Map external field names to Clinomic names using custom + default aliases."""
    result = {}
    for key, value in raw.items():
        # Custom mapping takes priority
        mapped = custom_mapping.get(key)
        if not mapped:
            mapped = DEFAULT_ALIASES.get(key)
        if not mapped:
            # Try case-insensitive match against Clinomic fields
            for cf in CLINOMIC_CBC_FIELDS | {'patient_id', 'lab_code', 'doctor_code'}:
                if key.lower() == cf.lower():
                    mapped = cf
                    break
        if mapped:
            result[mapped] = value
        # Fields that don't map are silently dropped
    return result


def coerce_numeric(data: dict) -> dict:
    """Convert string values to float where possible (analyzers often send strings)."""
    out = {}
    for k, v in data.items():
        if k in ('Sex', 'patient_id', 'lab_code', 'doctor_code'):
            out[k] = v
            continue
        if isinstance(v, (int, float)):
            out[k] = v
        elif isinstance(v, str):
            try:
                out[k] = float(v.strip())
            except (ValueError, AttributeError):
                out[k] = v
        else:
            out[k] = v
    return out


def parse_json(body: bytes, field_mapping: dict) -> dict:
    """Parse a REST JSON payload. Expects either a flat dict or {cbc: {...}, patient_id: ...}."""
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise ParseError(f"Invalid JSON: {e}")

    # Support nested {cbc: {...}} or flat structure
    if isinstance(data, dict) and 'cbc' in data:
        flat = {**data['cbc']}
        for k in ('patient_id', 'patientId', 'lab_code', 'labCode', 'doctor_code', 'doctorCode', 'Age', 'Sex'):
            if k in data:
                flat[k] = data[k]
    elif isinstance(data, dict):
        flat = data
    else:
        raise ParseError("JSON payload must be an object")

    mapped = apply_field_mapping(flat, field_mapping)
    return coerce_numeric(mapped)


def parse_csv(body: bytes, field_mapping: dict) -> dict:
    """Parse a single-row CSV (header + one data row). Multi-row returns first row only."""
    try:
        text = body.decode('utf-8-sig')  # handle BOM from Excel
        reader = csv.DictReader(io.StringIO(text))
        row = next(reader)
    except (UnicodeDecodeError, StopIteration) as e:
        raise ParseError(f"Invalid CSV: {e}")

    mapped = apply_field_mapping(dict(row), field_mapping)
    return coerce_numeric(mapped)


def parse_hl7v2(body: bytes, field_mapping: dict) -> dict:
    """
    Parse an HL7 v2.x ORU^R01 message and extract CBC observations.

    Minimal parser — handles the common Indian analyzer output format
    without requiring python-hl7 dependency. For production analyzer
    integrations, a full HL7 engine (Mirth/Rhapsody) should sit in front.
    """
    try:
        text = body.decode('utf-8', errors='replace')
    except Exception as e:
        raise ParseError(f"Cannot decode HL7 body: {e}")

    # HL7 uses \r as segment separator (some systems use \n or \r\n)
    segments = re.split(r'[\r\n]+', text.strip())

    extracted = {}

    for seg in segments:
        fields = seg.split('|')
        seg_type = fields[0] if fields else ''

        # PID segment: patient demographics
        if seg_type == 'PID' and len(fields) > 8:
            # PID-3: patient ID, PID-7: DOB (used to calc age), PID-8: sex
            if fields[3]:
                extracted['patient_id'] = fields[3].split('^')[0]
            if fields[8]:
                sex_raw = fields[8].strip().upper()
                extracted['Sex'] = 'M' if sex_raw.startswith('M') else 'F'

        # OBX segment: observation result
        if seg_type == 'OBX' and len(fields) > 5:
            # OBX-3: observation identifier (e.g., "718-7^Hemoglobin^LN")
            # OBX-5: observation value
            obs_id = fields[3]
            obs_value = fields[5]
            # Extract the text name from the identifier
            parts = obs_id.split('^')
            obs_name = parts[1] if len(parts) > 1 else parts[0]
            extracted[obs_name] = obs_value

    if not extracted:
        raise ParseError("No OBX segments found in HL7 message")

    mapped = apply_field_mapping(extracted, field_mapping)
    return coerce_numeric(mapped)


def parse_fhir_r4(body: bytes, field_mapping: dict) -> dict:
    """
    Parse a FHIR R4 Bundle or single Observation resource.

    Extracts CBC values from Observation resources by matching LOINC codes
    or display names to Clinomic fields.
    """
    LOINC_TO_FIELD = {
        '718-7': 'Hb', '789-8': 'RBC', '4544-3': 'HCT',
        '787-2': 'MCV', '785-6': 'MCH', '786-4': 'MCHC',
        '788-0': 'RDW', '6690-2': 'WBC', '777-3': 'Platelets',
        '751-8': 'Neutrophils', '731-0': 'Lymphocytes',
        '30525-0': 'Age', '76689-9': 'Sex',
    }

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise ParseError(f"Invalid FHIR JSON: {e}")

    extracted = {}

    # Handle Bundle or single resource
    entries = []
    if data.get('resourceType') == 'Bundle':
        entries = [e.get('resource', {}) for e in data.get('entry', [])]
    elif data.get('resourceType') == 'Observation':
        entries = [data]
    else:
        raise ParseError(f"Unexpected FHIR resourceType: {data.get('resourceType')}")

    for resource in entries:
        if resource.get('resourceType') != 'Observation':
            continue

        # Get the code (LOINC or display)
        coding = resource.get('code', {}).get('coding', [])
        loinc_code = None
        display = None
        for c in coding:
            if c.get('system', '').endswith('/loinc'):
                loinc_code = c.get('code')
            display = display or c.get('display')

        field = None
        if loinc_code and loinc_code in LOINC_TO_FIELD:
            field = LOINC_TO_FIELD[loinc_code]
        elif display:
            field = DEFAULT_ALIASES.get(display)

        if not field:
            continue

        # Extract value
        if 'valueQuantity' in resource:
            extracted[field] = resource['valueQuantity'].get('value')
        elif 'valueString' in resource:
            extracted[field] = resource['valueString']

    # Extract patient reference
    if entries:
        subject = entries[0].get('subject', {})
        ref = subject.get('reference', '')
        if ref.startswith('Patient/'):
            extracted['patient_id'] = ref.replace('Patient/', '')

    if not extracted:
        raise ParseError("No CBC observations found in FHIR resource")

    # Apply custom mapping on top
    mapped = apply_field_mapping(extracted, field_mapping)
    return coerce_numeric(mapped)


PARSERS = {
    'json': parse_json,
    'csv': parse_csv,
    'hl7v2': parse_hl7v2,
    'fhir_r4': parse_fhir_r4,
}

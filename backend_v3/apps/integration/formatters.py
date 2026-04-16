"""
Outbound formatters — convert Clinomic screening results into formats
the external LIS can consume and append to the patient record.
"""

import json
from datetime import datetime, timezone


def format_json(screening_data: dict) -> tuple[str, str]:
    """Return (body, content_type) for REST JSON callback."""
    payload = {
        'screening_id': screening_data['id'],
        'patient_id': screening_data['patientId'],
        'risk_class': screening_data['label'],
        'risk_label': screening_data['labelText'],
        'probabilities': screening_data['probabilities'],
        'recommendation': screening_data['recommendation'],
        'indices': screening_data.get('indices', {}),
        'rules_fired': screening_data.get('rulesFired', []),
        'narrative': screening_data.get('narrative', ''),
        'model_version': screening_data.get('modelVersion', ''),
        'screened_at': datetime.now(timezone.utc).isoformat(),
        'source': 'clinomic-b12-screening',
    }
    return json.dumps(payload), 'application/json'


def format_hl7v2(screening_data: dict) -> tuple[str, str]:
    """
    Return (body, content_type) as an HL7 v2 ORU^R01 result message.

    Minimal — includes MSH, PID, OBR, and OBX segments for the screening result.
    Real production should use a full HL7 engine; this covers common integration needs.
    """
    now = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    pid = screening_data.get('patientId', '')
    risk = screening_data.get('labelText', '')
    risk_class = screening_data.get('label', 0)
    recommendation = screening_data.get('recommendation', '')

    segments = [
        f"MSH|^~\\&|CLINOMIC|B12SCREENING|LIS|LAB|{now}||ORU^R01|{screening_data.get('id', '')}|P|2.5",
        f"PID|1||{pid}",
        f"OBR|1||{screening_data.get('id', '')}|B12-SCREEN^B12 Deficiency Screening^CLINOMIC",
        f"OBX|1|ST|B12RISK^B12 Risk Classification^CLINOMIC||{risk}||||||F",
        f"OBX|2|NM|B12RISKCLASS^B12 Risk Class^CLINOMIC||{risk_class}||||||F",
        f"OBX|3|ST|B12REC^B12 Recommendation^CLINOMIC||{recommendation}||||||F",
    ]

    # Add probability OBX segments
    probs = screening_data.get('probabilities', {})
    seq = 4
    for key, val in probs.items():
        segments.append(
            f"OBX|{seq}|NM|B12PROB_{key.upper()}^B12 {key} probability^CLINOMIC||{val:.4f}||||||F"
        )
        seq += 1

    body = '\r'.join(segments) + '\r'
    return body, 'application/hl7-v2'


def format_fhir_r4(screening_data: dict) -> tuple[str, str]:
    """Return (body, content_type) as a FHIR R4 DiagnosticReport."""
    now = datetime.now(timezone.utc).isoformat()
    pid = screening_data.get('patientId', '')
    risk = screening_data.get('labelText', '')
    risk_class = screening_data.get('label', 0)
    probs = screening_data.get('probabilities', {})

    # Map risk class to a SNOMED code (approximate)
    snomed_map = {
        1: {'code': '260415000', 'display': 'Not detected'},
        2: {'code': '419984006', 'display': 'Inconclusive'},
        3: {'code': '260373001', 'display': 'Detected'},
    }
    snomed = snomed_map.get(risk_class, {'code': '261665006', 'display': 'Unknown'})

    report = {
        'resourceType': 'DiagnosticReport',
        'id': screening_data.get('id', ''),
        'status': 'final',
        'category': [{
            'coding': [{
                'system': 'http://terminology.hl7.org/CodeSystem/v2-0074',
                'code': 'HM',
                'display': 'Hematology',
            }],
        }],
        'code': {
            'coding': [{
                'system': 'http://clinomiclabs.com/fhir/screening',
                'code': 'B12-DEFICIENCY-SCREEN',
                'display': 'B12 Deficiency Screening',
            }],
            'text': 'B12 Deficiency Screening (AI-assisted)',
        },
        'subject': {'reference': f'Patient/{pid}'},
        'effectiveDateTime': now,
        'issued': now,
        'conclusion': f'{risk} — {screening_data.get("recommendation", "")}',
        'conclusionCode': [{
            'coding': [{
                'system': 'http://snomed.info/sct',
                'code': snomed['code'],
                'display': snomed['display'],
            }],
            'text': risk,
        }],
        'result': [],
    }

    # Add probability observations as contained resources
    for key, val in probs.items():
        obs = {
            'resourceType': 'Observation',
            'id': f'prob-{key}',
            'status': 'final',
            'code': {
                'coding': [{
                    'system': 'http://clinomiclabs.com/fhir/screening',
                    'code': f'B12-PROB-{key.upper()}',
                    'display': f'B12 {key} probability',
                }],
            },
            'valueQuantity': {
                'value': round(val, 4),
                'unit': 'probability',
                'system': 'http://unitsofmeasure.org',
                'code': '1',
            },
        }
        report.setdefault('contained', []).append(obs)
        report['result'].append({'reference': f'#prob-{key}'})

    return json.dumps(report), 'application/fhir+json'


def format_csv(screening_data: dict) -> tuple[str, str]:
    """Return (body, content_type) as a single-row CSV."""
    probs = screening_data.get('probabilities', {})
    headers = ['screening_id', 'patient_id', 'risk_class', 'risk_label',
               'prob_normal', 'prob_borderline', 'prob_deficient',
               'recommendation', 'model_version', 'screened_at']
    values = [
        screening_data.get('id', ''),
        screening_data.get('patientId', ''),
        str(screening_data.get('label', '')),
        screening_data.get('labelText', ''),
        str(probs.get('normal', '')),
        str(probs.get('borderline', '')),
        str(probs.get('deficient', '')),
        screening_data.get('recommendation', ''),
        screening_data.get('modelVersion', ''),
        datetime.now(timezone.utc).isoformat(),
    ]
    body = ','.join(headers) + '\n' + ','.join(values) + '\n'
    return body, 'text/csv'


FORMATTERS = {
    'json': format_json,
    'csv': format_csv,
    'hl7v2': format_hl7v2,
    'fhir_r4': format_fhir_r4,
}

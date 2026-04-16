"""
Integration engine — the core pipeline that processes inbound LIS data.

    inbound payload → parse → map fields → predict → format result → callback

This runs synchronously for webhook/API calls and can also be invoked
from a Celery task for batch/file-based integrations.
"""

import hashlib
import logging
import time

import requests

from apps.screening.ml_engine import get_ml_engine, MLModelNotReadyError
from apps.screening.narrative import NarrativeEngine
from apps.screening.models import (
    Screening, ScreeningStatus, RiskClass, Patient, Lab, Doctor,
)
from apps.core.audit import log_phi_access

from .parsers import PARSERS, ParseError, CLINOMIC_CBC_FIELDS
from .formatters import FORMATTERS
from .models import IntegrationEndpoint, IntegrationLog

logger = logging.getLogger('clinomic.integration')


class IntegrationError(Exception):
    """Raised when the integration pipeline fails at any stage."""
    def __init__(self, message, stage='unknown'):
        self.stage = stage
        super().__init__(message)


def process_inbound(endpoint: IntegrationEndpoint, raw_body: bytes, request=None):
    """
    Full integration pipeline: parse → predict → persist → format → callback.

    Returns (screening_data_dict, outbound_body, content_type) on success.
    Raises IntegrationError on failure.
    All outcomes are logged to IntegrationLog.
    """
    t0 = time.monotonic()
    raw_hash = hashlib.sha256(raw_body).hexdigest()

    try:
        # 1. Parse inbound payload
        parser = PARSERS.get(endpoint.inbound_format)
        if not parser:
            raise IntegrationError(f"Unsupported inbound format: {endpoint.inbound_format}", 'parse')

        parsed = parser(raw_body, endpoint.field_mapping or {})

        # 2. Extract metadata
        patient_id = parsed.pop('patient_id', None)
        lab_code = parsed.pop('lab_code', None) or endpoint.default_lab_code
        doctor_code = parsed.pop('doctor_code', None) or endpoint.default_doctor_code

        if not patient_id:
            raise IntegrationError("patient_id is required but not found in payload", 'parse')
        if not lab_code:
            raise IntegrationError("lab_code is required (set in payload or endpoint defaults)", 'parse')

        # 3. Validate CBC fields
        cbc = {}
        for field in CLINOMIC_CBC_FIELDS:
            val = parsed.get(field)
            if val is not None:
                cbc[field] = val

        required_min = {'Hb', 'RBC', 'MCV', 'MCH'}
        missing = required_min - set(cbc.keys())
        if missing:
            raise IntegrationError(
                f"Missing required CBC fields: {', '.join(sorted(missing))}. "
                f"Got: {', '.join(sorted(cbc.keys()))}. "
                f"Check your field_mapping configuration.",
                'parse',
            )

        # 4. Run ML prediction
        engine = get_ml_engine()
        result = engine.predict(cbc)

        # 5. Generate narrative
        narrative_engine = NarrativeEngine()
        narrative = narrative_engine.generate(
            risk_class=result['riskClass'],
            label_text=result['labelText'],
            probabilities=result['probabilities'],
            rules_fired=result['rulesFired'],
            indices=result['indices'],
            cbc_snapshot=cbc,
            age=int(cbc.get('Age', 0)),
            sex=str(cbc.get('Sex', 'M')),
            patient_id=patient_id,
        )

        # 6. Resolve lab + doctor + patient and persist
        lab = Lab.objects.filter(code=lab_code).first()
        if not lab:
            raise IntegrationError(f"Lab with code '{lab_code}' not found", 'persist')

        doctor = None
        if doctor_code:
            doctor = Doctor.objects.filter(code=doctor_code, is_active=True).first()

        patient, _ = Patient.objects.get_or_create(
            patient_id=patient_id,
            defaults={'name_encrypted': '', 'age_encrypted': '', 'sex_encrypted': ''},
        )

        recommendation = _recommendation(result['riskClass'])

        screening = Screening.objects.create(
            patient=patient,
            lab=lab,
            doctor=doctor,
            performed_by=f"integration:{endpoint.name}",
            risk_class=result['riskClass'],
            label_text=result['labelText'],
            probabilities=result['probabilities'],
            rules_fired=result['rulesFired'],
            cbc_snapshot=cbc,
            indices=result['indices'],
            model_version=result.get('modelVersion', ''),
            model_artifact_hash=result.get('modelHash', ''),
            request_hash=raw_hash,
            response_hash=hashlib.sha256(str(result).encode()).hexdigest(),
            screening_hash=hashlib.sha256(
                f"{patient_id}:{str(cbc)}:{str(result)}".encode()
            ).hexdigest(),
            narrative=narrative,
            status=ScreeningStatus.IN_PROGRESS if endpoint.auto_approve else ScreeningStatus.PENDING,
        )

        # 7. Audit log
        if request:
            log_phi_access(
                request, patient_id, 'PHI_INTEGRATION_PREDICT',
                {'screening_id': str(screening.id), 'endpoint': endpoint.name},
            )

        # 8. Format outbound
        screening_data = {
            'id': str(screening.id),
            'patientId': patient_id,
            'label': result['riskClass'],
            'labelText': result['labelText'],
            'probabilities': result['probabilities'],
            'indices': result['indices'],
            'rulesFired': result['rulesFired'],
            'recommendation': recommendation,
            'narrative': narrative,
            'modelVersion': result.get('modelVersion', ''),
        }

        formatter = FORMATTERS.get(endpoint.outbound_format, FORMATTERS['json'])
        outbound_body, content_type = formatter(screening_data)

        # 9. Callback to LIS (if configured)
        callback_error = None
        if endpoint.callback_url:
            try:
                headers = {'Content-Type': content_type}
                headers.update(endpoint.callback_headers or {})
                resp = requests.post(
                    endpoint.callback_url,
                    data=outbound_body,
                    headers=headers,
                    timeout=15,
                )
                resp.raise_for_status()
            except requests.RequestException as e:
                callback_error = str(e)
                logger.warning(
                    'integration.callback_failed',
                    endpoint=endpoint.name,
                    url=endpoint.callback_url,
                    error=str(e),
                )

        # 10. Log success
        duration = int((time.monotonic() - t0) * 1000)
        IntegrationLog.objects.create(
            endpoint=endpoint,
            direction='inbound',
            status='callback_error' if callback_error else 'success',
            raw_hash=raw_hash,
            mapped_fields={k: str(v) for k, v in cbc.items()},
            error_detail=callback_error or '',
            screening_id=screening.id,
            duration_ms=duration,
        )

        return screening_data, outbound_body, content_type

    except ParseError as e:
        duration = int((time.monotonic() - t0) * 1000)
        IntegrationLog.objects.create(
            endpoint=endpoint, direction='inbound', status='parse_error',
            raw_hash=raw_hash, error_detail=str(e), duration_ms=duration,
        )
        raise IntegrationError(str(e), 'parse')

    except MLModelNotReadyError as e:
        duration = int((time.monotonic() - t0) * 1000)
        IntegrationLog.objects.create(
            endpoint=endpoint, direction='inbound', status='predict_error',
            raw_hash=raw_hash, error_detail=str(e), duration_ms=duration,
        )
        raise IntegrationError(str(e), 'predict')

    except IntegrationError:
        raise

    except Exception as e:
        duration = int((time.monotonic() - t0) * 1000)
        IntegrationLog.objects.create(
            endpoint=endpoint, direction='inbound', status='predict_error',
            raw_hash=raw_hash, error_detail=str(e), duration_ms=duration,
        )
        logger.exception('integration.unhandled_error', endpoint=endpoint.name)
        raise IntegrationError(str(e), 'unknown')


def _recommendation(risk_class: int) -> str:
    if risk_class == 3:
        return "Serum B12 measurement recommended. Clinical correlation advised."
    elif risk_class == 2:
        return "Consider serum B12 measurement if clinically indicated."
    return "B12 deficiency unlikely based on CBC parameters."

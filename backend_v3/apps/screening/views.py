"""
Screening API views.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.core.audit import log_phi_access
from apps.core.crypto import encrypt_field
from apps.core.exceptions import MLModelNotReadyError
from apps.core.models import Role
from apps.core.permissions import HasRole, HasAPIKeyScope, IsAdmin, IsMFAVerified

from .ml_engine import get_ml_engine, predict_async
from .models import BulkImportJob, Consent, Doctor, Lab, Patient, Screening, ScreeningStatus
from .narrative_engine import NarrativeEngine
from .ws_broadcast import broadcast_high_risk_alert, broadcast_new_screening, broadcast_status_change
from .serializers import (
    ConsentRecordSerializer,
    ConsentSerializer,
    DoctorSerializer,
    LabSerializer,
    ScreeningRequestSerializer,
    ScreeningSerializer,
)

import structlog
logger = structlog.get_logger(__name__)


class ScreeningRateThrottle(UserRateThrottle):
    rate = '50/minute'


class PredictView(APIView):
    """
    B12 screening prediction endpoint.

    POST /api/screening/predict
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole, HasAPIKeyScope]
    required_roles = [Role.LAB, Role.DOCTOR, Role.ADMIN]
    required_api_key_scope = 'screening:write'
    throttle_classes = [ScreeningRateThrottle]

    def post(self, request):
        serializer = ScreeningRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        patient_id = data['patientId']
        if not patient_id.strip():
            return Response(
                {'error': 'patientId is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate consent (if provided) before running the model
        consent_id = data.get('consentId')
        if consent_id:
            now_utc = datetime.now(timezone.utc)
            try:
                consent_obj = Consent.objects.get(id=consent_id)
            except Consent.DoesNotExist:
                return Response(
                    {'error': 'Consent record not found'},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Auto-expire if the timestamp has passed
            if consent_obj.expires_at and consent_obj.expires_at < now_utc:
                if consent_obj.status == 'active':
                    consent_obj.status = 'expired'
                    consent_obj.save(update_fields=['status', 'updated_at'])
                return Response(
                    {'error': 'Patient consent has expired. Please obtain renewed consent before screening.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            if consent_obj.status == 'revoked':
                return Response(
                    {'error': 'Patient consent has been revoked'},
                    status=status.HTTP_403_FORBIDDEN
                )

            if consent_obj.status != 'active':
                return Response(
                    {'error': 'No valid patient consent on file'},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Get CBC data
        cbc = data['cbc']

        # Run ML prediction (synchronous)
        try:
            engine = get_ml_engine()
            result = engine.predict(cbc)
        except MLModelNotReadyError as e:
            logger.error(f"ML model not ready for prediction: {e}")
            return Response(
                {'error': 'ML screening service unavailable. Models not loaded.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except Exception as e:
            logger.exception("Model prediction failed")
            return Response(
                {'error': 'Prediction failed. Please try again or contact support.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # Generate clinical narrative
        narrative_engine = NarrativeEngine()
        narrative_text = narrative_engine.generate(
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

        now = datetime.now(timezone.utc)

        # Get or create lab (use default if not specified)
        lab = None
        if data.get('labId'):
            lab = Lab.objects.filter(code=data['labId']).first()
        if not lab:
            lab = Lab.objects.filter(is_active=True).first()

        # Get or create doctor
        doctor = None
        if data.get('doctorId'):
            doctor = Doctor.objects.filter(code=data['doctorId']).first()

        # Get or create patient with encrypted PHI fields
        patient, _ = Patient.objects.update_or_create(
            patient_id=patient_id,
            defaults={
                'name_encrypted': encrypt_field((data.get('patientName') or '').strip()),
                'age_encrypted': encrypt_field(str(int(cbc.get('Age', 0)))),
                'sex_encrypted': encrypt_field(str(cbc.get('Sex', 'M'))),
                'lab': lab,
                'referring_doctor': doctor,
            }
        )

        # Compute hashes for reproducibility (deterministic key order)
        request_hash = hashlib.sha256(
            f"{patient_id}:{json.dumps(cbc, sort_keys=True)}".encode()
        ).hexdigest()
        response_hash = hashlib.sha256(
            json.dumps(result, sort_keys=True).encode()
        ).hexdigest()

        screening_id = uuid.uuid4()
        screening_hash = hashlib.sha256(
            f"{screening_id}:{request_hash}:{response_hash}".encode()
        ).hexdigest()

        # Create screening record
        screening = Screening.objects.create(
            id=screening_id,
            patient=patient,
            lab=lab,
            doctor=doctor,
            performed_by=request.user.username,
            risk_class=result['riskClass'],
            label_text=result['labelText'],
            probabilities=result['probabilities'],
            rules_fired=result['rulesFired'],
            cbc_snapshot=cbc,
            indices=result['indices'],
            model_version=result['modelVersion'],
            model_artifact_hash=result['modelArtifactHash'],
            request_hash=request_hash,
            response_hash=response_hash,
            screening_hash=screening_hash,
            consent_id=data.get('consentId'),
            narrative=narrative_text,
        )

        # Generate recommendation text
        risk_class = result['riskClass']
        if risk_class == 3:
            recommendation = "Serum B12 measurement recommended. Clinical correlation advised."
        elif risk_class == 2:
            recommendation = "Consider serum B12 measurement if clinically indicated."
        else:
            recommendation = "B12 deficiency unlikely based on CBC parameters."

        # Broadcast WebSocket notifications
        broadcast_new_screening(str(screening.id), result['riskClass'], 'pending')
        if result['riskClass'] == 3:
            broadcast_high_risk_alert(
                str(screening.id),
                result['riskClass'],
                result['labelText'],
                doctor_id=str(doctor.id) if doctor else None,
            )

        # Fire usage increment, HTTP webhooks, and high-risk alert (non-blocking)
        org = getattr(request, 'tenant', None)
        org_id = str(org.id) if org else None
        if org_id:
            from apps.billing.tasks import increment_usage, trigger_webhook, send_high_risk_alert
            increment_usage.delay(org_id, str(screening.id))
            # C1: fire HTTP webhook for every completed screening
            trigger_webhook(org, 'screening.completed', {
                'screening_id': str(screening.id),
                'patient_id': patient_id,
                'risk_class': result['riskClass'],
                'label': result['labelText'],
                'model_version': result['modelVersion'],
            })
            # C2: send email alert for high-risk (class 3) screenings
            if result['riskClass'] == 3:
                send_high_risk_alert.delay(
                    str(screening.id),
                    org_id,
                    str(doctor.id) if doctor else None,
                )

        log_phi_access(request, patient_id, 'PHI_PREDICT', {
            'screening_id': str(screening.id),
            'risk_class': result['riskClass'],
            'model_version': result['modelVersion'],
        })

        return Response({
            'id': str(screening.id),
            'patientId': patient_id,
            'label': result['riskClass'],
            'labelText': result['labelText'],
            'probabilities': result['probabilities'],
            'indices': result['indices'],
            'recommendation': recommendation,
            'rulesFired': result['rulesFired'],
            'modelVersion': result['modelVersion'],
            'narrative': narrative_text,
        })


class LabListView(APIView):
    """
    List all labs.

    GET /api/screening/labs
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.ADMIN]

    def get(self, request):
        labs = Lab.objects.filter(is_active=True).prefetch_related('doctors', 'screenings')
        serializer = LabSerializer(labs, many=True)
        return Response(serializer.data)


class DoctorListView(APIView):
    """
    List doctors, optionally filtered by lab.

    GET /api/screening/doctors?labId=LAB-001
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.ADMIN, Role.LAB]

    def get(self, request):
        lab_id = request.query_params.get('labId')

        queryset = Doctor.objects.filter(is_active=True).select_related('lab')
        if lab_id:
            queryset = queryset.filter(lab__code=lab_id)

        serializer = DoctorSerializer(queryset, many=True)
        return Response(serializer.data)


class CaseListView(APIView):
    """
    List screening cases with filters.

    GET /api/screening/cases?doctorId=D001&labId=LAB-001&page=1&page_size=50
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole, HasAPIKeyScope]
    required_roles = [Role.ADMIN, Role.LAB]
    required_api_key_scope = 'screening:read'

    def get(self, request):
        doctor_id = request.query_params.get('doctorId')
        lab_id = request.query_params.get('labId')

        queryset = Screening.objects.select_related(
            'patient', 'lab', 'doctor'
        ).order_by('-created_at')

        if doctor_id:
            queryset = queryset.filter(doctor__code=doctor_id)
        if lab_id:
            queryset = queryset.filter(lab__code=lab_id)

        # H7: proper pagination (default 50, max 200, client-controlled)
        try:
            page = max(1, int(request.query_params.get('page', 1)))
            page_size = min(200, max(1, int(request.query_params.get('page_size', 50))))
        except (ValueError, TypeError):
            page = 1
            page_size = 50

        total = queryset.count()
        offset = (page - 1) * page_size
        page_qs = queryset[offset:offset + page_size]

        serializer = ScreeningSerializer(page_qs, many=True)
        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': serializer.data,
        })


class ConsentRecordView(APIView):
    """
    Record patient consent.

    POST /api/screening/consent/record
    """
    permission_classes = [IsAuthenticated, IsMFAVerified]

    def post(self, request):
        serializer = ConsentRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Get default lab (first active lab in the system)
        default_lab = Lab.objects.filter(is_active=True).first()
        if not default_lab:
            return Response(
                {'error': 'No active lab found in the system'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get or create patient
        patient, _ = Patient.objects.get_or_create(
            patient_id=data['patientId'],
            defaults={
                'name_encrypted': '',
                'age_encrypted': encrypt_field('0'),
                'sex_encrypted': encrypt_field('M'),
                'lab': default_lab,
            }
        )

        now = datetime.now(timezone.utc)

        consent = Consent.objects.create(
            patient=patient,
            consent_type=data.get('consentType', 'screening'),
            consent_text=data['consentText'],
            consented_by=request.user.username,
            consent_method=data.get('consentMethod', 'verbal'),
            status='active',
            consented_at=now,
        )

        return Response({
            'id': str(consent.id),
            'status': 'recorded',
        })


class ConsentStatusView(APIView):
    """
    Get consent status for a patient.

    GET /api/screening/consent/status/{patientId}
    """
    permission_classes = [IsAuthenticated, IsMFAVerified]

    def get(self, request, patient_id):
        try:
            patient = Patient.objects.get(patient_id=patient_id)
            consent = Consent.objects.filter(
                patient=patient,
                status='active'
            ).order_by('-consented_at').first()

            if consent:
                now_utc = datetime.now(timezone.utc)
                is_expired = bool(consent.expires_at and consent.expires_at < now_utc)

                # Keep DB status in sync
                if is_expired:
                    consent.status = 'expired'
                    consent.save(update_fields=['status', 'updated_at'])

                log_phi_access(request, patient_id, 'PHI_CONSENT_READ', {
                    'has_consent': not is_expired,
                    'is_expired': is_expired,
                })
                return Response({
                    'hasConsent': not is_expired,
                    'consentId': str(consent.id),
                    'consentType': consent.consent_type,
                    'consentedAt': consent.consented_at.isoformat(),
                    'expiresAt': consent.expires_at.isoformat() if consent.expires_at else None,
                    'isExpired': is_expired,
                })
            else:
                log_phi_access(request, patient_id, 'PHI_CONSENT_READ', {
                    'has_consent': False,
                })
                return Response({'hasConsent': False})

        except Patient.DoesNotExist:
            log_phi_access(request, patient_id, 'PHI_CONSENT_READ', {
                'has_consent': False,
                'note': 'patient not found',
            })
            return Response({'hasConsent': False})


class ConsentRevokeView(APIView):
    """
    Revoke patient consent.

    POST /api/screening/consent/revoke/{consentId}

    Authorization:
    - ADMIN: always permitted.
    - LAB: permitted for any patient in the tenant (lab users manage all
      patient records within their organisation).
    - DOCTOR: permitted only if they are the patient's referring doctor.
    - All other roles: 403.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified]

    def post(self, request, consent_id):
        try:
            consent = Consent.objects.select_related('patient__referring_doctor').get(id=consent_id)
        except Consent.DoesNotExist:
            return Response(
                {'error': 'Consent not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Authorization check
        user_role = request.user.role
        if user_role == Role.DOCTOR:
            doctor = Doctor.objects.filter(email=request.user.email, is_active=True).first()
            if not doctor or consent.patient.referring_doctor_id != doctor.id:
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
        elif user_role not in (Role.ADMIN, Role.LAB):
            return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        consent.status = 'revoked'
        consent.revoked_at = datetime.now(timezone.utc)
        consent.save()

        return Response({'status': 'revoked'})


class WorkQueueView(APIView):
    """
    LAB triage work queue.

    GET /api/screening/queue?status=pending
    Returns per-status counts + items for the requested status.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB, Role.ADMIN]

    def get(self, request):
        queue_status = request.query_params.get('status', ScreeningStatus.PENDING)
        if queue_status not in ScreeningStatus.values:
            return Response(
                {'error': f"Invalid status. Choices: {ScreeningStatus.values}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        base_qs = Screening.objects.all()
        counts = {
            'pending': base_qs.filter(status=ScreeningStatus.PENDING).count(),
            'in_progress': base_qs.filter(status=ScreeningStatus.IN_PROGRESS).count(),
            'completed': base_qs.filter(status=ScreeningStatus.COMPLETED).count(),
        }

        # H7: honour client-supplied page_size (default 50, max 200)
        try:
            page_size = min(200, max(1, int(request.query_params.get('page_size', 50))))
            page = max(1, int(request.query_params.get('page', 1)))
        except (ValueError, TypeError):
            page_size = 50
            page = 1
        offset = (page - 1) * page_size

        items_qs = base_qs.filter(status=queue_status).select_related(
            'patient', 'lab', 'doctor'
        ).order_by('-created_at')[offset:offset + page_size]

        items = []
        for s in items_qs:
            items.append({
                'id': str(s.id),
                'patientId': s.patient.patient_id if s.patient else None,
                'patientInitials': (s.patient.name[0] + '.' if s.patient and s.patient.name else None),
                'labId': s.lab.code if s.lab else None,
                'doctorName': s.doctor.name if s.doctor else None,
                'riskClass': s.risk_class,
                'labelText': s.label_text,
                'status': s.status,
                'createdAt': s.created_at.isoformat(),
                'performedBy': s.performed_by,
            })

        total_for_status = base_qs.filter(status=queue_status).count()
        return Response({
            'counts': counts,
            'items': items,
            'pagination': {'page': page, 'page_size': page_size, 'total': total_for_status},
        })


class ScreeningStatusView(APIView):
    """
    Transition a screening's work-queue status.

    PATCH /api/screening/cases/<uuid>/status
    Body: { "status": "in_progress" | "completed" | "pending" }
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB, Role.ADMIN]

    ALLOWED_TRANSITIONS = {
        ScreeningStatus.PENDING: [ScreeningStatus.IN_PROGRESS, ScreeningStatus.COMPLETED],
        ScreeningStatus.IN_PROGRESS: [ScreeningStatus.COMPLETED, ScreeningStatus.PENDING],
        ScreeningStatus.COMPLETED: [],  # Terminal state
    }

    def patch(self, request, screening_id):
        try:
            screening = Screening.objects.get(id=screening_id)
        except Screening.DoesNotExist:
            return Response({'error': 'Screening not found'}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get('status')
        if not new_status:
            return Response({'error': 'status is required'}, status=status.HTTP_400_BAD_REQUEST)

        allowed = self.ALLOWED_TRANSITIONS.get(screening.status, [])
        if new_status not in allowed:
            return Response(
                {'error': f"Cannot transition from '{screening.status}' to '{new_status}'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = screening.status
        screening.status = new_status
        screening.save(update_fields=['status'])

        broadcast_status_change(
            str(screening.id), old_status, new_status, screening.risk_class,
        )

        return Response({'id': str(screening.id), 'status': screening.status})


class ReviewScreeningView(APIView):
    """
    Mark a screening as reviewed and optionally add a clinical note.

    PATCH /api/screening/cases/<uuid>/review
    Body: { "clinical_note": "..." }  (optional)
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.DOCTOR, Role.ADMIN]

    def patch(self, request, screening_id):
        try:
            screening = Screening.objects.select_related('patient', 'doctor').get(id=screening_id)
        except Screening.DoesNotExist:
            return Response({'error': 'Screening not found'}, status=status.HTTP_404_NOT_FOUND)

        # DOCTOR isolation: can only review their own patients' screenings
        if request.user.role == Role.DOCTOR:
            doctor = Doctor.objects.filter(email=request.user.email, is_active=True).first()
            if not doctor or screening.doctor_id != doctor.id:
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        screening.is_reviewed = True
        screening.reviewed_at = datetime.now(timezone.utc)
        screening.reviewed_by = request.user.username
        if 'clinical_note' in request.data:
            screening.clinical_note = request.data['clinical_note']
        screening.save(update_fields=['is_reviewed', 'reviewed_at', 'reviewed_by', 'clinical_note'])

        log_phi_access(
            request,
            screening.patient.patient_id if screening.patient else '*',
            'PHI_REVIEW',
            {'screening_id': str(screening_id)},
        )

        return Response({
            'is_reviewed': screening.is_reviewed,
            'reviewed_at': screening.reviewed_at.isoformat(),
            'reviewed_by': screening.reviewed_by,
            'clinical_note': screening.clinical_note,
        })


class ExplainView(APIView):
    """
    SHAP explainability for a screening prediction.

    GET /api/screening/cases/<uuid:screening_id>/explain
    Returns feature importances ranked by absolute SHAP value.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB, Role.DOCTOR, Role.ADMIN]

    def get(self, request, screening_id):
        try:
            screening = Screening.objects.select_related('patient', 'doctor').get(id=screening_id)
        except Screening.DoesNotExist:
            return Response({'error': 'Screening not found'}, status=status.HTTP_404_NOT_FOUND)

        # DOCTOR isolation: can only see their own patients' screenings
        if request.user.role == Role.DOCTOR:
            doctor = Doctor.objects.filter(email=request.user.email, is_active=True).first()
            if not doctor or screening.doctor_id != doctor.id:
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        indices = screening.indices or {}
        shap_values = indices.get('shap_values', {})

        if not shap_values:
            return Response(
                {'error': 'SHAP values not available for this screening'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Sort by absolute value, descending
        ranked = sorted(
            shap_values.items(),
            key=lambda x: abs(x[1]),
            reverse=True,
        )

        features = [
            {
                'feature': name,
                'shap_value': value,
                'abs_shap_value': abs(value),
                'direction': 'risk_increasing' if value > 0 else 'risk_decreasing',
            }
            for name, value in ranked
        ]

        log_phi_access(
            request,
            screening.patient.patient_id if screening.patient else '*',
            'PHI_EXPLAIN',
            {'screening_id': str(screening_id)},
        )

        return Response({
            'screeningId': str(screening.id),
            'riskClass': screening.risk_class,
            'labelText': screening.label_text,
            'features': features,
        })


class BulkImportView(APIView):
    """
    Submit a CSV file for asynchronous bulk screening import.

    POST /api/screening/bulk-import
    Content-Type: multipart/form-data
    Body field: file (CSV)

    CSV required columns:
        patient_id, patient_name, lab_id, doctor_id,
        hb, rbc, hct, mcv, mch, mchc, rdw, wbc, plt, neu_pct, lym_pct,
        age, sex

    Returns:
        { "jobId": "<uuid>", "status": "pending", "totalRows": N }
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB, Role.ADMIN]

    def post(self, request):
        uploaded = request.FILES.get('file')
        if not uploaded:
            return Response({'error': 'No file uploaded. Provide a CSV as field "file".'}, status=status.HTTP_400_BAD_REQUEST)

        if not uploaded.name.lower().endswith('.csv'):
            return Response({'error': 'Only CSV files are accepted.'}, status=status.HTTP_400_BAD_REQUEST)

        # Read CSV text (limit to 10 MB)
        MAX_BYTES = 10 * 1024 * 1024
        if uploaded.size > MAX_BYTES:
            return Response({'error': 'File too large (max 10 MB).'}, status=status.HTTP_400_BAD_REQUEST)

        csv_text = uploaded.read().decode('utf-8-sig')  # handle BOM

        # Quick column validation before enqueuing
        import csv as csv_mod, io
        reader = csv_mod.DictReader(io.StringIO(csv_text))
        headers = {f.strip().lower() for f in (reader.fieldnames or [])}
        required = {'patient_id', 'hb', 'rbc', 'hct', 'mcv', 'mch', 'mchc', 'rdw', 'wbc', 'plt', 'neu_pct', 'lym_pct', 'age', 'sex'}
        missing = required - headers
        if missing:
            return Response(
                {'error': f"Missing CSV columns: {sorted(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create job record
        job = BulkImportJob.objects.create(submitted_by=request.user.username)

        # Get default lab code from the requesting user's lab context
        lab_code = request.query_params.get('labId', '')

        # Enqueue Celery task
        from .tasks import process_bulk_import
        process_bulk_import.delay(str(job.id), csv_text, lab_code, request.user.username)

        log_phi_access(request, '*', 'BULK_IMPORT_SUBMIT', {'job_id': str(job.id)})

        return Response({
            'jobId': str(job.id),
            'status': job.status,
            'totalRows': job.total_rows,
        }, status=status.HTTP_202_ACCEPTED)


class BulkImportStatusView(APIView):
    """
    Poll the status of a bulk import job.

    GET /api/screening/bulk-import/<job_id>/status
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB, Role.ADMIN]

    def get(self, request, job_id):
        try:
            job = BulkImportJob.objects.get(id=job_id)
        except BulkImportJob.DoesNotExist:
            return Response({'error': 'Job not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            'jobId': str(job.id),
            'status': job.status,
            'totalRows': job.total_rows,
            'processedRows': job.processed_rows,
            'failedRows': job.failed_rows,
            'errors': job.error_detail,
            'createdAt': job.created_at.isoformat(),
            'updatedAt': job.updated_at.isoformat(),
        })


# ── FHIR R4 LOINC → CBC field mapping ─────────────────────────────────────────
_LOINC_TO_CBC = {
    '718-7':   'Hb_g_dL',           # Haemoglobin (g/dL)
    '789-8':   'RBC_million_uL',     # Erythrocytes (10^6/μL)
    '4544-3':  'HCT_percent',        # Haematocrit (%)
    '787-2':   'MCV_fL',             # MCV (fL)
    '785-6':   'MCH_pg',             # MCH (pg)
    '786-4':   'MCHC_g_dL',          # MCHC (g/dL)
    '788-0':   'RDW_percent',        # RDW (%)
    '6690-2':  'WBC_10_3_uL',        # Leukocytes (10^3/μL)
    '777-3':   'Platelets_10_3_uL',  # Platelets (10^3/μL)
    '770-8':   'Neutrophils_percent',# Neutrophils (%)
    '736-9':   'Lymphocytes_percent',# Lymphocytes (%)
}


class FHIRBundleView(APIView):
    """
    Accept a FHIR R4 Bundle containing a Patient resource and CBC Observation
    resources, run the B12 screening prediction, and return a FHIR
    DiagnosticReport-style response.

    POST /api/screening/fhir/bundle
    Content-Type: application/json

    Minimal bundle structure:
    {
      "resourceType": "Bundle",
      "type": "transaction",
      "entry": [
        { "resource": { "resourceType": "Patient", "id": "...", "birthDate": "1985-04-12",
                        "gender": "male", "identifier": [{"value": "P001"}] } },
        { "resource": { "resourceType": "Observation", "code": {"coding": [{"system": "http://loinc.org", "code": "718-7"}]},
                        "valueQuantity": {"value": 14.5} } },
        ...
      ]
    }
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB, Role.DOCTOR, Role.ADMIN]

    def post(self, request):
        bundle = request.data
        if bundle.get('resourceType') != 'Bundle':
            return Response(
                {'error': 'Expected resourceType "Bundle"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        entries = bundle.get('entry', [])
        patient_resource = None
        observations = {}   # cbc_key → value

        for entry in entries:
            resource = entry.get('resource', {})
            rtype = resource.get('resourceType')

            if rtype == 'Patient' and patient_resource is None:
                patient_resource = resource

            elif rtype == 'Observation':
                codings = resource.get('code', {}).get('coding', [])
                for coding in codings:
                    if coding.get('system') == 'http://loinc.org':
                        loinc = coding.get('code', '')
                        if loinc in _LOINC_TO_CBC:
                            value_q = resource.get('valueQuantity') or resource.get('valueRatio')
                            if value_q and 'value' in value_q:
                                observations[_LOINC_TO_CBC[loinc]] = float(value_q['value'])

        if not patient_resource:
            return Response({'error': 'Bundle must contain a Patient resource'}, status=status.HTTP_400_BAD_REQUEST)

        required_obs = set(_LOINC_TO_CBC.values())
        missing_obs = required_obs - set(observations.keys())
        if missing_obs:
            return Response(
                {'error': f'Missing Observation LOINC codes mapping to: {sorted(missing_obs)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Extract patient demographics
        identifiers = patient_resource.get('identifier', [])
        patient_id = identifiers[0].get('value', '') if identifiers else patient_resource.get('id', '')
        if not patient_id:
            return Response({'error': 'Patient resource must have an identifier or id'}, status=status.HTTP_400_BAD_REQUEST)

        # Calculate age from birthDate (YYYY-MM-DD)
        from datetime import date
        birth_str = patient_resource.get('birthDate', '')
        try:
            birth_date = date.fromisoformat(birth_str)
            today = date.today()
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        except (ValueError, TypeError):
            return Response({'error': 'Patient.birthDate must be YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)

        gender = patient_resource.get('gender', 'unknown').lower()
        sex = 'M' if gender in ('male', 'm') else 'F'

        # Build CBC dict for ML engine
        cbc = dict(observations)
        cbc['Age'] = age
        cbc['Sex'] = sex

        # Run prediction
        try:
            engine = get_ml_engine()
            result = engine.predict(cbc)
        except Exception as exc:
            logger.exception("fhir_predict_failed", error=str(exc))
            return Response({'error': 'Prediction failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Persist patient and screening
        import hashlib as _hashlib, uuid as _uuid
        from datetime import datetime, timezone

        lab = Lab.objects.filter(is_active=True).first()
        patient, _ = Patient.objects.update_or_create(
            patient_id=patient_id,
            defaults={
                'name_encrypted': encrypt_field(patient_resource.get('name', [{}])[0].get('text', '') if patient_resource.get('name') else ''),
                'age_encrypted': encrypt_field(str(age)),
                'sex_encrypted': encrypt_field(sex),
                'lab': lab,
            }
        )

        req_hash  = _hashlib.sha256(f"{patient_id}:{cbc}".encode()).hexdigest()
        resp_hash = _hashlib.sha256(f"{result}".encode()).hexdigest()
        sid       = _uuid.uuid4()
        s_hash    = _hashlib.sha256(f"{sid}:{req_hash}:{resp_hash}".encode()).hexdigest()

        screening = Screening.objects.create(
            id=sid,
            patient=patient,
            lab=lab,
            performed_by=request.user.username,
            risk_class=result['riskClass'],
            label_text=result['labelText'],
            probabilities=result['probabilities'],
            rules_fired=result['rulesFired'],
            cbc_snapshot=cbc,
            indices=result['indices'],
            model_version=result['modelVersion'],
            model_artifact_hash=result['modelArtifactHash'],
            request_hash=req_hash,
            response_hash=resp_hash,
            screening_hash=s_hash,
        )

        log_phi_access(request, patient_id, 'PHI_FHIR_PREDICT', {'screening_id': str(screening.id)})

        # Fire HTTP webhook + high-risk alert for FHIR screenings
        org = getattr(request, 'tenant', None)
        fhir_org_id = str(org.id) if org else None
        if fhir_org_id:
            from apps.billing.tasks import trigger_webhook, send_high_risk_alert
            trigger_webhook(org, 'screening.completed', {
                'screening_id': str(screening.id),
                'patient_id': patient_id,
                'risk_class': result['riskClass'],
                'label': result['labelText'],
                'model_version': result['modelVersion'],
                'source': 'fhir',
            })
            if result['riskClass'] == 3:
                send_high_risk_alert.delay(str(screening.id), fhir_org_id, None)

        # Return FHIR DiagnosticReport-style structure
        risk_map = {1: 'normal', 2: 'borderline', 3: 'deficient'}
        return Response({
            'resourceType': 'DiagnosticReport',
            'id': str(screening.id),
            'status': 'final',
            'subject': {'reference': f'Patient/{patient_id}'},
            'issued': screening.created_at.isoformat(),
            'conclusion': result['labelText'],
            'conclusionCode': [{
                'coding': [{
                    'system': 'https://clinomiclabs.com/fhir/CodeSystem/b12-risk',
                    'code': risk_map.get(result['riskClass'], 'unknown'),
                    'display': result['labelText'],
                }]
            }],
            'extension': [{
                'url': 'https://clinomiclabs.com/fhir/StructureDefinition/b12-probabilities',
                'valueString': str(result['probabilities']),
            }],
        }, status=status.HTTP_201_CREATED)


# ── Admin Lab Management ────────────────────────────────────────────────────────

class AdminLabView(APIView):
    """
    List and create labs (tenant-scoped).

    GET  /api/screening/admin/labs   — list all labs
    POST /api/screening/admin/labs   — create a new lab
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, IsAdmin]

    def get(self, request):
        labs = Lab.objects.all().order_by('name')
        data = [
            {
                'id': str(l.id),
                'code': l.code,
                'name': l.name,
                'tier': l.tier,
                'contact_email': l.contact_email,
                'is_active': l.is_active,
                'created_at': l.created_at.isoformat(),
            }
            for l in labs
        ]
        return Response(data)

    def post(self, request):
        for field in ['code', 'name']:
            if not request.data.get(field):
                return Response({'error': f'{field} is required'}, status=status.HTTP_400_BAD_REQUEST)

        code = request.data['code'].strip()
        if Lab.objects.filter(code__iexact=code).exists():
            return Response({'error': 'Lab code already exists'}, status=status.HTTP_400_BAD_REQUEST)

        lab = Lab.objects.create(
            code=code,
            name=request.data['name'].strip(),
            tier=request.data.get('tier', 'standard'),
            contact_email=(request.data.get('contact_email') or '').strip(),
        )
        return Response({
            'id': str(lab.id),
            'code': lab.code,
            'name': lab.name,
            'tier': lab.tier,
            'contact_email': lab.contact_email,
            'is_active': lab.is_active,
        }, status=status.HTTP_201_CREATED)


class AdminLabDetailView(APIView):
    """
    Update or deactivate a lab.

    PATCH  /api/screening/admin/labs/<lab_id>  — update fields
    DELETE /api/screening/admin/labs/<lab_id>  — soft-deactivate
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, IsAdmin]

    def _get_lab(self, lab_id):
        try:
            return Lab.objects.get(id=lab_id)
        except Lab.DoesNotExist:
            return None

    def patch(self, request, lab_id):
        lab = self._get_lab(lab_id)
        if not lab:
            return Response({'error': 'Lab not found'}, status=status.HTTP_404_NOT_FOUND)

        for field in ['name', 'tier', 'contact_email', 'is_active']:
            if field in request.data:
                setattr(lab, field, request.data[field])
        lab.save()
        return Response({
            'id': str(lab.id),
            'code': lab.code,
            'name': lab.name,
            'tier': lab.tier,
            'contact_email': lab.contact_email,
            'is_active': lab.is_active,
        })

    def delete(self, request, lab_id):
        lab = self._get_lab(lab_id)
        if not lab:
            return Response({'error': 'Lab not found'}, status=status.HTTP_404_NOT_FOUND)
        lab.is_active = False
        lab.save(update_fields=['is_active', 'updated_at'])
        return Response({'detail': 'Lab deactivated'})


# ── Admin Doctor Management ─────────────────────────────────────────────────────

class AdminDoctorView(APIView):
    """
    List and create doctors (tenant-scoped).

    GET  /api/screening/admin/doctors   — list all doctors
    POST /api/screening/admin/doctors   — create a new doctor
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, IsAdmin]

    def get(self, request):
        lab_id = request.query_params.get('labId')
        qs = Doctor.objects.select_related('lab').order_by('name')
        if lab_id:
            qs = qs.filter(lab__code=lab_id)
        data = [
            {
                'id': str(d.id),
                'code': d.code,
                'name': d.name,
                'department': d.department,
                'specialization': d.specialization,
                'email': d.email,
                'lab_id': str(d.lab_id),
                'lab_code': d.lab.code,
                'lab_name': d.lab.name,
                'is_active': d.is_active,
                'created_at': d.created_at.isoformat(),
            }
            for d in qs
        ]
        return Response(data)

    def post(self, request):
        for field in ['code', 'name', 'lab_id']:
            if not request.data.get(field):
                return Response({'error': f'{field} is required'}, status=status.HTTP_400_BAD_REQUEST)

        code = request.data['code'].strip()
        if Doctor.objects.filter(code__iexact=code).exists():
            return Response({'error': 'Doctor code already exists'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            lab = Lab.objects.get(id=request.data['lab_id'])
        except Lab.DoesNotExist:
            return Response({'error': 'Lab not found'}, status=status.HTTP_400_BAD_REQUEST)

        doctor = Doctor.objects.create(
            code=code,
            name=request.data['name'].strip(),
            department=(request.data.get('department') or '').strip(),
            specialization=(request.data.get('specialization') or '').strip(),
            email=(request.data.get('email') or '').strip(),
            lab=lab,
        )
        return Response({
            'id': str(doctor.id),
            'code': doctor.code,
            'name': doctor.name,
            'department': doctor.department,
            'specialization': doctor.specialization,
            'email': doctor.email,
            'lab_id': str(doctor.lab_id),
            'is_active': doctor.is_active,
        }, status=status.HTTP_201_CREATED)


class AdminDoctorDetailView(APIView):
    """
    Update or deactivate a doctor.

    PATCH  /api/screening/admin/doctors/<doctor_id>  — update fields
    DELETE /api/screening/admin/doctors/<doctor_id>  — soft-deactivate
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, IsAdmin]

    def _get_doctor(self, doctor_id):
        try:
            return Doctor.objects.select_related('lab').get(id=doctor_id)
        except Doctor.DoesNotExist:
            return None

    def patch(self, request, doctor_id):
        doctor = self._get_doctor(doctor_id)
        if not doctor:
            return Response({'error': 'Doctor not found'}, status=status.HTTP_404_NOT_FOUND)

        for field in ['name', 'department', 'specialization', 'email', 'is_active']:
            if field in request.data:
                setattr(doctor, field, request.data[field])

        if 'lab_id' in request.data:
            try:
                doctor.lab = Lab.objects.get(id=request.data['lab_id'])
            except Lab.DoesNotExist:
                return Response({'error': 'Lab not found'}, status=status.HTTP_400_BAD_REQUEST)

        doctor.save()
        return Response({
            'id': str(doctor.id),
            'code': doctor.code,
            'name': doctor.name,
            'department': doctor.department,
            'specialization': doctor.specialization,
            'email': doctor.email,
            'lab_id': str(doctor.lab_id),
            'is_active': doctor.is_active,
        })

    def delete(self, request, doctor_id):
        doctor = self._get_doctor(doctor_id)
        if not doctor:
            return Response({'error': 'Doctor not found'}, status=status.HTTP_404_NOT_FOUND)
        doctor.is_active = False
        doctor.save(update_fields=['is_active', 'updated_at'])
        return Response({'detail': 'Doctor deactivated'})

"""
Screening API views.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Case, When, IntegerField
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.core.audit import log_phi_access
from apps.core.crypto import encrypt_field
from apps.core.exceptions import MLModelNotReadyError
from apps.core.models import Role
from apps.core.permissions import HasRole, HasAPIKeyScope, IsAdmin, IsMFAVerified, IsOrgManager

from .ml_engine import get_ml_engine, predict_async
from .models import BulkImportJob, Consent, Doctor, Lab, Patient, Screening, ScreeningStatus
from .narrative_engine import NarrativeEngine
from .ws_broadcast import broadcast_high_risk_alert, broadcast_new_screening, broadcast_status_change
from .serializers import (
    AdminDoctorUpdateSerializer,
    AdminLabUpdateSerializer,
    ConsentRecordSerializer,
    ConsentSerializer,
    DoctorSerializer,
    LabSerializer,
    ReviewScreeningSerializer,
    ScreeningRequestSerializer,
    ScreeningSerializer,
)

import structlog
logger = structlog.get_logger(__name__)


class ScreeningRateThrottle(UserRateThrottle):
    rate = '50/minute'

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception:
            # Fail closed — never silently allow unlimited screening predictions
            # when the throttle backend is down. Setting self.history=[] prevents
            # the AttributeError DRF would otherwise hit in wait().
            logger.error("throttle_cache_error: ScreeningRateThrottle denied (fail-closed)")
            self.history = []
            return False


SCREENING_IDEMPOTENCY_TTL = 300  # 5 minutes — dedup window for identical (patient, CBC)


class PredictView(APIView):
    """
    B12 screening prediction endpoint.

    POST /api/screening/predict

    The request lifecycle is:
        1. validate payload + patientId
        2. validate consent (if provided) — returns 422 with a stable
           error code so the frontend can distinguish consent issues
           from auth errors
        3. look up an idempotent hit in cache — if found, return the
           existing screening
        4. run the ML engine + narrative generator
        5. resolve lab / doctor / patient, persist the screening
        6. fire side effects (websocket, webhook, high-risk alert,
           analytics cache bust, idempotency key, PHI audit log)

    Each stage is a private helper so the orchestrator stays readable.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole, HasAPIKeyScope]
    required_roles = [Role.LAB, Role.DOCTOR]
    required_api_key_scope = 'screening:write'
    throttle_classes = [ScreeningRateThrottle]

    @staticmethod
    def _recommendation(risk_class: int) -> str:
        if risk_class == 3:
            return "Serum B12 measurement recommended. Clinical correlation advised."
        elif risk_class == 2:
            return "Consider serum B12 measurement if clinically indicated."
        return "B12 deficiency unlikely based on CBC parameters."

    @staticmethod
    def _idempotency_key(patient_id: str, cbc: dict) -> tuple[str, str]:
        """Return (full_cache_key, sha256_hex) for a (patient, CBC) pair."""
        h = hashlib.sha256(
            f"{patient_id}:{json.dumps(cbc, sort_keys=True)}".encode()
        ).hexdigest()
        return f"screening:idemp:{h}", h

    def _validate_consent(self, consent_id, patient_id):
        """
        Return (consent_obj_or_None, error_response_or_None).

        A non-None error_response means the caller should short-circuit
        with that 422 immediately. These are PROCESSING errors — not
        authorisation errors — so the frontend can render a "renew
        consent" prompt instead of a "permission denied" banner.
        """
        if not consent_id:
            return None, None

        now_utc = datetime.now(timezone.utc)
        try:
            consent_obj = Consent.objects.get(id=consent_id)
        except (Consent.DoesNotExist, ValueError):
            return None, Response(
                {'error': 'Consent record not found', 'code': 'consent_not_found'},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if consent_obj.patient.patient_id != patient_id:
            return None, Response(
                {'error': 'Consent does not match the specified patient',
                 'code': 'consent_patient_mismatch'},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if consent_obj.expires_at and consent_obj.expires_at < now_utc:
            if consent_obj.status == 'active':
                consent_obj.status = 'expired'
                consent_obj.save(update_fields=['status', 'updated_at'])
            return None, Response(
                {'error': 'Patient consent has expired. Please obtain renewed consent before screening.',
                 'code': 'consent_expired'},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if consent_obj.status == 'revoked':
            return None, Response(
                {'error': 'Patient consent has been revoked', 'code': 'consent_revoked'},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if consent_obj.status != 'active':
            return None, Response(
                {'error': 'No valid patient consent on file', 'code': 'consent_inactive'},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return consent_obj, None

    def _lookup_idempotent(self, cache_key, patient_id):
        """
        Return a Response if an identical prior screening exists in the
        TTL window, or None to continue with a fresh prediction.
        """
        cached_screening_id = None
        try:
            cached_screening_id = cache.get(cache_key)
        except Exception:
            pass  # cache miss is fine — just skip dedup

        if not cached_screening_id:
            return None

        existing = Screening.objects.filter(id=cached_screening_id).select_related('patient').first()
        if not existing:
            return None

        logger.info("idempotent_hit", screening_id=str(existing.id), cache_key=cache_key)
        return Response({
            'id': str(existing.id),
            'patientId': patient_id,
            'label': existing.risk_class,
            'labelText': existing.label_text,
            'probabilities': existing.probabilities,
            'indices': existing.indices,
            'recommendation': self._recommendation(existing.risk_class),
            'rulesFired': existing.rules_fired,
            'modelVersion': existing.model_version,
            'narrative': existing.narrative,
            'duplicate': True,
        })

    def _run_prediction(self, cbc):
        """
        Return (result_dict, error_response_or_None).

        Fast-failure for "model not loaded" is a 503 so clients back off
        for a reload; any other exception becomes a 500.
        """
        try:
            engine = get_ml_engine()
            return engine.predict(cbc), None
        except MLModelNotReadyError as e:
            logger.error(f"ML model not ready for prediction: {e}")
            return None, Response(
                {'error': 'ML screening service unavailable. Models not loaded.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except Exception:
            logger.exception("Model prediction failed")
            return None, Response(
                {'error': 'Prediction failed. Please try again or contact support.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @staticmethod
    def _generate_narrative(result, cbc, patient_id):
        narrative_engine = NarrativeEngine()
        return narrative_engine.generate(
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

    def _persist_screening(self, request, data, cbc, result, narrative_text, patient_id):
        """
        Resolve lab / doctor / patient, write the Screening row.

        Return (screening, doctor, lab, error_response_or_None).
        """
        lab = None
        if data.get('labId'):
            lab = Lab.objects.filter(code=data['labId']).first()
        if not lab:
            return None, None, None, Response(
                {'error': 'labId is required or no matching lab found'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        doctor = None
        if data.get('doctorId'):
            doctor = Doctor.objects.filter(code=data['doctorId']).first()

        try:
            patient, _ = Patient.objects.update_or_create(
                patient_id=patient_id,
                lab=lab,
                defaults={
                    'name_encrypted': encrypt_field((data.get('patientName') or '').strip()),
                    'age_encrypted': encrypt_field(str(int(cbc.get('Age', 0)))),
                    'sex_encrypted': encrypt_field(str(cbc.get('Sex', 'M'))),
                    'referring_doctor': doctor,
                }
            )
        except Exception:
            logger.exception("Patient create/update failed for %s", patient_id)
            return None, None, None, Response(
                {'error': 'Failed to save patient record. Please contact support.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

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
        return screening, doctor, lab, None

    def _dispatch_side_effects(self, request, screening, result, doctor, patient_id, cache_key):
        """Non-blocking post-save work: websocket, webhook, analytics cache bust, idempotency stash, PHI audit."""
        broadcast_new_screening(str(screening.id), result['riskClass'], 'pending')
        if result['riskClass'] == 3:
            broadcast_high_risk_alert(
                str(screening.id),
                result['riskClass'],
                result['labelText'],
                doctor_id=str(doctor.id) if doctor else None,
            )

        org = getattr(request, 'tenant', None)
        org_id = str(org.id) if org else None
        if org_id:
            from apps.billing.tasks import increment_usage, trigger_webhook, send_high_risk_alert
            increment_usage.delay(org_id, str(screening.id))
            try:
                trigger_webhook(org, 'screening.completed', {
                    'screening_id': str(screening.id),
                    'patient_id': patient_id,
                    'risk_class': result['riskClass'],
                    'label': result['labelText'],
                    'model_version': result['modelVersion'],
                })
            except Exception:
                logger.exception("trigger_webhook failed for screening %s", screening.id)
            if result['riskClass'] == 3:
                send_high_risk_alert.delay(
                    str(screening.id),
                    org_id,
                    str(doctor.id) if doctor else None,
                )

        from apps.analytics.cache import invalidate_analytics_caches
        invalidate_analytics_caches(
            user_id=request.user.pk,
            doctor_code=doctor.code if doctor else None,
        )

        try:
            cache.set(cache_key, str(screening.id), timeout=SCREENING_IDEMPOTENCY_TTL)
        except Exception:
            pass  # idempotency cache is best-effort

        log_phi_access(request, patient_id, 'PHI_PREDICT', {
            'screening_id': str(screening.id),
            'risk_class': result['riskClass'],
            'model_version': result['modelVersion'],
        })

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

        _, consent_err = self._validate_consent(data.get('consentId'), patient_id)
        if consent_err is not None:
            return consent_err

        cbc = data['cbc']
        idempotency_cache_key, _ = self._idempotency_key(patient_id, cbc)

        cached_response = self._lookup_idempotent(idempotency_cache_key, patient_id)
        if cached_response is not None:
            return cached_response

        result, pred_err = self._run_prediction(cbc)
        if pred_err is not None:
            return pred_err

        narrative_text = self._generate_narrative(result, cbc, patient_id)

        screening, doctor, _lab, persist_err = self._persist_screening(
            request, data, cbc, result, narrative_text, patient_id
        )
        if persist_err is not None:
            return persist_err

        self._dispatch_side_effects(
            request, screening, result, doctor, patient_id, idempotency_cache_key
        )

        return Response({
            'id': str(screening.id),
            'patientId': patient_id,
            'label': result['riskClass'],
            'labelText': result['labelText'],
            'probabilities': result['probabilities'],
            'indices': result['indices'],
            'recommendation': self._recommendation(result['riskClass']),
            'rulesFired': result['rulesFired'],
            'modelVersion': result['modelVersion'],
            'narrative': narrative_text,
        })


class _LabListPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class LabListView(APIView):
    """
    List all labs.

    GET /api/screening/labs?page=1&page_size=50
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB, Role.SUPER_ADMIN]

    def get(self, request):
        labs = Lab.objects.filter(is_active=True).annotate(
            doctors_count=Count('doctors', distinct=True),
            cases_count=Count('screenings', distinct=True),
        ).order_by('id')
        paginator = _LabListPagination()
        page = paginator.paginate_queryset(labs, request, view=self)
        serializer = LabSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class DoctorListView(APIView):
    """
    List doctors, optionally filtered by lab.

    GET /api/screening/doctors?labId=LAB-001
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB]

    def get(self, request):
        lab_id = request.query_params.get('labId')

        queryset = Doctor.objects.filter(is_active=True).select_related('lab').annotate(
            cases_count=Count('screenings'),
        )
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
    required_roles = [Role.LAB]
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


def _validate_lab_association(user):
    """
    Ensure the requesting user has an active lab association in the current
    tenant.  Returns ``(lab, None)`` on success or ``(None, Response)`` with
    an HTTP 400 error when the association is missing — this is a data /
    configuration issue, **not** a permissions issue, so we intentionally
    avoid 403.
    """
    if user.role == Role.LAB:
        lab = Lab.objects.filter(is_active=True).order_by('created_at').first()
        if not lab:
            return None, Response(
                {'error': 'No active lab found for your account. Contact your administrator.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return lab, None
    if user.role == Role.DOCTOR and user.email:
        doctor = Doctor.objects.filter(email=user.email, is_active=True).select_related('lab').first()
        if not doctor or not doctor.lab:
            return None, Response(
                {'error': 'No active lab assignment found for your account. Contact your administrator.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return doctor.lab, None
    return None, None


class ConsentRecordView(APIView):
    """
    Record patient consent.

    POST /api/screening/consent/record
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB, Role.DOCTOR]

    def post(self, request):
        # Validate that the user is associated with a lab in this tenant
        assoc_lab, err_response = _validate_lab_association(request.user)
        if err_response:
            return err_response

        serializer = ConsentRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Resolve lab: use labId from request if provided, otherwise fall back
        # to the lab resolved from the user's association (e.g. DOCTOR role).
        lab = None
        if data.get('labId'):
            lab = Lab.objects.filter(code=data['labId']).first()
        if not lab:
            lab = assoc_lab
        if not lab:
            return Response(
                {'error': 'Could not determine lab. Provide a valid labId or ensure your account is linked to a lab.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get or create patient scoped to lab
        patient, _ = Patient.objects.get_or_create(
            patient_id=data['patientId'],
            lab=lab,
            defaults={
                'name_encrypted': '',
                'age_encrypted': encrypt_field('0'),
                'sex_encrypted': encrypt_field('M'),
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
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB, Role.DOCTOR]

    def get(self, request, patient_id):
        # Validate that the user is associated with a lab in this tenant
        _, err_response = _validate_lab_association(request.user)
        if err_response:
            return err_response

        try:
            patient = Patient.objects.get(patient_id=patient_id)
            consent = Consent.objects.filter(
                patient=patient,
                status='active'
            ).order_by('-consented_at').first()

            if consent:
                now_utc = datetime.now(timezone.utc)
                is_expired = bool(consent.expires_at and consent.expires_at < now_utc)

                # Note: expired consents are transitioned by Celery beat
                # (purge_expired_consents). GET must not mutate state.

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
        elif user_role != Role.LAB:
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
    required_roles = [Role.LAB]

    def get(self, request):
        queue_status = request.query_params.get('status', ScreeningStatus.PENDING)
        if queue_status not in ScreeningStatus.values:
            return Response(
                {'error': f"Invalid status. Choices: {ScreeningStatus.values}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        base_qs = Screening.objects.all()

        # Redis-cached aggregate counts (single query, 10s TTL)
        tenant_schema = getattr(request, 'tenant', None)
        cache_key = f'wq_counts:{tenant_schema.schema_name if tenant_schema else "default"}'
        counts = cache.get(cache_key)
        if counts is None:
            counts_agg = base_qs.aggregate(
                pending=Count(Case(When(status=ScreeningStatus.PENDING, then=1), output_field=IntegerField())),
                in_progress=Count(Case(When(status=ScreeningStatus.IN_PROGRESS, then=1), output_field=IntegerField())),
                completed=Count(Case(When(status=ScreeningStatus.COMPLETED, then=1), output_field=IntegerField())),
            )
            counts = {
                'pending': counts_agg['pending'],
                'in_progress': counts_agg['in_progress'],
                'completed': counts_agg['completed'],
            }
            cache.set(cache_key, counts, timeout=10)

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
    required_roles = [Role.LAB]

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
    required_roles = [Role.DOCTOR, Role.LAB]

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

        serializer = ReviewScreeningSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        screening.is_reviewed = True
        screening.reviewed_at = datetime.now(timezone.utc)
        screening.reviewed_by = request.user.username
        if 'clinical_note' in serializer.validated_data:
            screening.clinical_note = serializer.validated_data['clinical_note']
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
    required_roles = [Role.LAB, Role.DOCTOR]

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
    required_roles = [Role.LAB]

    def post(self, request):
        uploaded = request.FILES.get('file')
        if not uploaded:
            return Response({'error': 'No file uploaded. Provide a CSV as field "file".'}, status=status.HTTP_400_BAD_REQUEST)

        if not uploaded.name.lower().endswith('.csv'):
            return Response({'error': 'Only CSV files are accepted.'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate file size BEFORE reading content into memory (DoS prevention)
        MAX_BYTES = 10 * 1024 * 1024
        if uploaded.size > MAX_BYTES:
            return Response({'error': 'File too large (max 10 MB).'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate file content type via magic bytes (not just extension)
        try:
            import magic
            header = uploaded.read(2048)
            uploaded.seek(0)
            mime = magic.from_buffer(header, mime=True)
            ALLOWED_MIMES = {'text/csv', 'text/plain', 'application/csv', 'application/octet-stream'}
            if mime not in ALLOWED_MIMES:
                return Response(
                    {'error': 'Invalid file type detected. Only CSV files are accepted.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ImportError:
            # python-magic-bin not installed — log warning but allow extension-validated CSV through.
            # Defence-in-depth: CSV column validation below catches non-CSV content.
            logger.warning("python-magic not installed; CSV magic-byte validation skipped")

        # Read with a hard cap to prevent memory exhaustion even if size header is spoofed
        raw_bytes = uploaded.read(MAX_BYTES + 1)
        if len(raw_bytes) > MAX_BYTES:
            return Response({'error': 'File too large (max 10 MB).'}, status=status.HTTP_400_BAD_REQUEST)
        csv_text = raw_bytes.decode('utf-8-sig')  # handle BOM

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

        # Get lab code from query params (REQUIRED) — validate before creating job
        lab_code = request.query_params.get('labId', '').strip()
        if not lab_code:
            return Response(
                {'error': 'labId query parameter is required for bulk import'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate lab exists
        from .models import Lab
        lab = Lab.objects.filter(code=lab_code, is_active=True).first()
        if not lab:
            return Response(
                {'error': 'labId not found or inactive'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create job record
        job = BulkImportJob.objects.create(submitted_by=request.user.username)

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
    required_roles = [Role.LAB]

    def get(self, request, job_id):
        try:
            job = BulkImportJob.objects.get(id=job_id, submitted_by=request.user.username)
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
# Keys must match the ML engine's expected column names (Hb, RBC, etc.),
# NOT the CBCSerializer field names (Hb_g_dL, RBC_million_uL, etc.)
# since the FHIR flow bypasses the serializer.
_LOINC_TO_CBC = {
    '718-7':   'Hb',           # Haemoglobin (g/dL)
    '789-8':   'RBC',          # Erythrocytes (10^6/μL)
    '4544-3':  'HCT',          # Haematocrit (%)
    '787-2':   'MCV',          # MCV (fL)
    '785-6':   'MCH',          # MCH (pg)
    '786-4':   'MCHC',         # MCHC (g/dL)
    '788-0':   'RDW',          # RDW (%)
    '6690-2':  'WBC',          # Leukocytes (10^3/μL)
    '777-3':   'Platelets',    # Platelets (10^3/μL)
    '770-8':   'Neutrophils',  # Neutrophils (%)
    '736-9':   'Lymphocytes',  # Lymphocytes (%)
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
    required_roles = [Role.LAB, Role.DOCTOR]

    def post(self, request):
        bundle = request.data
        if bundle.get('resourceType') != 'Bundle':
            return Response(
                {'error': 'Expected resourceType "Bundle"'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get lab from query param or bundle (REQUIRED - no silent fallback!)
        lab_code = request.query_params.get('labId')
        if not lab_code:
            return Response(
                {'error': 'labId query parameter is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        lab = Lab.objects.filter(code=lab_code, is_active=True).first()
        if not lab:
            return Response(
                {'error': 'labId not found or inactive'},
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

        patient, _ = Patient.objects.update_or_create(
            patient_id=patient_id,
            lab=lab,
            defaults={
                'name_encrypted': encrypt_field(patient_resource.get('name', [{}])[0].get('text', '') if patient_resource.get('name') else ''),
                'age_encrypted': encrypt_field(str(age)),
                'sex_encrypted': encrypt_field(sex),
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
            try:
                trigger_webhook(org, 'screening.completed', {
                    'screening_id': str(screening.id),
                    'patient_id': patient_id,
                    'risk_class': result['riskClass'],
                    'label': result['labelText'],
                    'model_version': result['modelVersion'],
                    'source': 'fhir',
                })
            except Exception:
                logger.exception("trigger_webhook failed for FHIR screening %s", screening.id)
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
            'extension': [
                {
                    'url': 'https://clinomiclabs.com/fhir/StructureDefinition/b12-probabilities',
                    'valueString': str(result['probabilities']),
                },
            ],
        }, status=status.HTTP_201_CREATED)


# ── Admin Lab Management ────────────────────────────────────────────────────────

class AdminLabView(APIView):
    """
    List and create labs (tenant-scoped).

    GET  /api/screening/admin/labs   — list all labs
    POST /api/screening/admin/labs   — create a new lab
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, IsOrgManager]

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
    permission_classes = [IsAuthenticated, IsMFAVerified, IsOrgManager]

    def _get_lab(self, lab_id):
        try:
            return Lab.objects.get(id=lab_id)
        except Lab.DoesNotExist:
            return None

    def patch(self, request, lab_id):
        lab = self._get_lab(lab_id)
        if not lab:
            return Response({'error': 'Lab not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AdminLabUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(lab, field, value)
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

        if request.query_params.get('permanent') == 'true':
            if lab.is_active:
                return Response(
                    {'error': 'Deactivate the lab first before permanently removing'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            lab.delete()
            return Response({'detail': 'Lab permanently removed'})

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
    permission_classes = [IsAuthenticated, IsMFAVerified, IsOrgManager]

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
    permission_classes = [IsAuthenticated, IsMFAVerified, IsOrgManager]

    def _get_doctor(self, doctor_id):
        try:
            return Doctor.objects.select_related('lab').get(id=doctor_id)
        except Doctor.DoesNotExist:
            return None

    def patch(self, request, doctor_id):
        doctor = self._get_doctor(doctor_id)
        if not doctor:
            return Response({'error': 'Doctor not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = AdminDoctorUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        if 'lab_id' in validated:
            try:
                doctor.lab = Lab.objects.get(id=validated.pop('lab_id'))
            except Lab.DoesNotExist:
                return Response({'error': 'Lab not found'}, status=status.HTTP_400_BAD_REQUEST)

        for field, value in validated.items():
            setattr(doctor, field, value)

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

        # ?permanent=true → hard-delete (only for already-inactive doctors)
        if request.query_params.get('permanent') == 'true':
            if doctor.is_active:
                return Response(
                    {'error': 'Deactivate the doctor first before permanently removing'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            doctor.delete()
            return Response({'detail': 'Doctor permanently removed'})

        doctor.is_active = False
        doctor.save(update_fields=['is_active', 'updated_at'])
        return Response({'detail': 'Doctor deactivated'})

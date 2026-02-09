"""
Screening API views.
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.core.crypto import encrypt_field
from apps.core.exceptions import MLModelNotReadyError
from apps.core.models import Role
from apps.core.permissions import HasRole

from .ml_engine import get_ml_engine, predict_async
from .models import Consent, Doctor, Lab, Patient, Screening
from .serializers import (
    ConsentRecordSerializer,
    ConsentSerializer,
    DoctorSerializer,
    LabSerializer,
    ScreeningRequestSerializer,
    ScreeningSerializer,
)

logger = logging.getLogger(__name__)


class ScreeningRateThrottle(UserRateThrottle):
    rate = '50/minute'


class PredictView(APIView):
    """
    B12 screening prediction endpoint.

    POST /api/screening/predict
    """
    permission_classes = [IsAuthenticated, HasRole]
    required_roles = [Role.LAB, Role.DOCTOR, Role.ADMIN]
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
                {'error': f'Prediction failed: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
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

        # Get or create patient with encrypted name
        patient, _ = Patient.objects.update_or_create(
            patient_id=patient_id,
            defaults={
                'name_encrypted': encrypt_field((data.get('patientName') or '').strip()),
                'age': int(cbc.get('Age', 0)),
                'sex': str(cbc.get('Sex', 'M')),
                'lab': lab,
                'referring_doctor': doctor,
            }
        )

        # Compute hashes for reproducibility
        request_hash = hashlib.sha256(
            f"{patient_id}:{cbc}".encode()
        ).hexdigest()
        response_hash = hashlib.sha256(
            f"{result}".encode()
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
        )

        # Generate recommendation text
        risk_class = result['riskClass']
        if risk_class == 3:
            recommendation = "Serum B12 measurement recommended. Clinical correlation advised."
        elif risk_class == 2:
            recommendation = "Consider serum B12 measurement if clinically indicated."
        else:
            recommendation = "B12 deficiency unlikely based on CBC parameters."

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
        })


class LabListView(APIView):
    """
    List all labs.

    GET /api/screening/labs
    """
    permission_classes = [IsAuthenticated, HasRole]
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
    permission_classes = [IsAuthenticated, HasRole]
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

    GET /api/screening/cases?doctorId=D001&labId=LAB-001
    """
    permission_classes = [IsAuthenticated, HasRole]
    required_roles = [Role.ADMIN, Role.LAB]

    def get(self, request):
        doctor_id = request.query_params.get('doctorId')
        lab_id = request.query_params.get('labId')

        queryset = Screening.objects.select_related(
            'patient', 'lab', 'doctor'
        ).order_by('-created_at')[:500]

        if doctor_id:
            queryset = queryset.filter(doctor__code=doctor_id)
        if lab_id:
            queryset = queryset.filter(lab__code=lab_id)

        serializer = ScreeningSerializer(queryset, many=True)
        return Response(serializer.data)


class ConsentRecordView(APIView):
    """
    Record patient consent.

    POST /api/screening/consent/record
    """
    permission_classes = [IsAuthenticated]

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
                'age': 0,
                'sex': 'M',
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
    permission_classes = [IsAuthenticated]

    def get(self, request, patient_id):
        try:
            patient = Patient.objects.get(patient_id=patient_id)
            consent = Consent.objects.filter(
                patient=patient,
                status='active'
            ).order_by('-consented_at').first()

            if consent:
                return Response({
                    'hasConsent': True,
                    'consentId': str(consent.id),
                    'consentType': consent.consent_type,
                    'consentedAt': consent.consented_at.isoformat(),
                })
            else:
                return Response({'hasConsent': False})

        except Patient.DoesNotExist:
            return Response({'hasConsent': False})


class ConsentRevokeView(APIView):
    """
    Revoke patient consent.

    POST /api/screening/consent/revoke/{consentId}
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, consent_id):
        try:
            consent = Consent.objects.get(id=consent_id)
            consent.status = 'revoked'
            consent.revoked_at = datetime.now(timezone.utc)
            consent.save()

            return Response({'status': 'revoked'})

        except Consent.DoesNotExist:
            return Response(
                {'error': 'Consent not found'},
                status=status.HTTP_404_NOT_FOUND
            )

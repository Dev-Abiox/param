"""
Analytics API views for dashboard and reporting.
"""

import logging
from datetime import datetime, timedelta, timezone

import structlog
from django.core.cache import cache
from django.db import connection
from django.db.models import Count
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.audit import log_phi_access
from apps.core.models import Role
from apps.core.permissions import HasRole, IsMFAVerified
from apps.screening.models import Doctor, Lab, Patient, Screening, ScreeningStatus
from apps.screening.serializers import ScreeningSerializer

logger = structlog.get_logger(__name__)


def _cache_key(*parts) -> str:
    """Build a tenant-scoped cache key."""
    schema = getattr(connection, 'schema_name', 'public')
    return "analytics:" + ":".join(str(p) for p in [schema, *parts])


class SummaryView(APIView):
    """
    Dashboard summary statistics.

    GET /api/analytics/summary
    For DOCTOR role: returns only their own stats filtered by doctor email.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.ADMIN, Role.LAB, Role.DOCTOR]

    def get(self, request):
        ck = _cache_key('summary', request.user.pk)
        cached = cache.get(ck)
        if cached is not None:
            logger.debug("cache_hit", key=ck)
            return Response(cached)

        # Base queryset
        queryset = Screening.objects.all()

        # For DOCTOR role, filter by their doctor record (matched by email)
        if request.user.role == Role.DOCTOR and request.user.email:
            doctor = Doctor.objects.filter(email=request.user.email, is_active=True).first()
            if doctor:
                queryset = queryset.filter(doctor=doctor)
            else:
                # No matching doctor record, return empty stats
                queryset = Screening.objects.none()

        # Total counts
        total_cases = queryset.count()
        normal_count = queryset.filter(risk_class=1).count()
        borderline_count = queryset.filter(risk_class=2).count()
        deficient_count = queryset.filter(risk_class=3).count()

        # Daily tests (last 24 hours)
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        daily_tests = queryset.filter(created_at__gte=since).count()

        # Recent cases
        recent_screenings = queryset.select_related(
            'patient'
        ).order_by('-created_at')[:20]

        recent = []
        for s in recent_screenings:
            if s.risk_class == 3:
                result_str = "High Risk"
            elif s.risk_class == 2:
                result_str = "Borderline"
            else:
                result_str = "Normal"

            recent.append({
                'id': str(s.id),
                'date': s.created_at.strftime('%Y-%m-%d'),
                'patientRef': s.patient.patient_id if s.patient else None,
                'mcv': s.cbc_snapshot.get('MCV', '-'),
                'result': result_str,
            })

        payload = {
            'totalCases': total_cases,
            'dailyTests': daily_tests,
            'modelMetrics': {
                'accuracy': 92,
                'recall': 88,
                'precision': 90,
                'f1Score': 89,
                'auc': 0.94,
                'version': 'v1.0.0',
            },
            'distribution': [
                {'name': 'Normal', 'value': normal_count, 'fill': '#10b981'},
                {'name': 'Borderline', 'value': borderline_count, 'fill': '#f59e0b'},
                {'name': 'Deficient', 'value': deficient_count, 'fill': '#ef4444'},
            ],
            'recentCases': recent,
        }
        cache.set(ck, payload, timeout=60)
        return Response(payload)


class LabStatsView(APIView):
    """
    Lab-level statistics.

    GET /api/analytics/labs
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.ADMIN]

    def get(self, request):
        ck = _cache_key('labs')
        cached = cache.get(ck)
        if cached is not None:
            logger.debug("cache_hit", key=ck)
            return Response(cached)

        labs = Lab.objects.filter(is_active=True).annotate(
            doctors_count=Count('doctors'),
            cases_count=Count('screenings')
        )

        result = []
        for lab in labs:
            result.append({
                'id': str(lab.id),
                'code': lab.code,
                'name': lab.name,
                'tier': lab.tier,
                'doctors': lab.doctors_count,
                'cases': lab.cases_count,
            })

        cache.set(ck, result, timeout=120)
        return Response(result)


class DoctorStatsView(APIView):
    """
    Doctor-level statistics.

    GET /api/analytics/doctors?labId=LAB-001
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.ADMIN, Role.LAB]

    def get(self, request):
        lab_id = request.query_params.get('labId', '')
        ck = _cache_key('doctors', lab_id or 'all')
        cached = cache.get(ck)
        if cached is not None:
            logger.debug("cache_hit", key=ck)
            return Response(cached)

        queryset = Doctor.objects.filter(is_active=True).annotate(
            cases_count=Count('screenings')
        ).select_related('lab')

        if lab_id:
            queryset = queryset.filter(lab__code=lab_id)

        result = []
        for doctor in queryset:
            result.append({
                'id': str(doctor.id),
                'code': doctor.code,
                'name': doctor.name,
                'dept': doctor.department or 'General',
                'cases': doctor.cases_count,
            })

        cache.set(ck, result, timeout=60)
        return Response(result)


class CaseStatsView(APIView):
    """
    Case-level details with patient info.

    GET /api/analytics/cases?doctorId=D001&labId=LAB-001

    Access rules:
    - DOCTOR: always sees only their own cases; doctorId param is ignored and
              rejected with 403 if it doesn't belong to the requesting user.
    - LAB/ADMIN: may filter by doctorId and labId query params.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.ADMIN, Role.LAB, Role.DOCTOR]

    def get(self, request):
        queryset = Screening.objects.select_related(
            'patient', 'lab', 'doctor'
        ).order_by('-created_at')

        if request.user.role == Role.DOCTOR:
            # DOCTOR role: derive identity from the authenticated user only.
            # Any doctorId query param is rejected — doctors cannot query other doctors.
            if request.query_params.get('doctorId'):
                return Response(
                    {'error': 'Doctors cannot filter by doctorId. Access is restricted to your own patients.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            doctor = Doctor.objects.filter(email=request.user.email, is_active=True).first()
            if not doctor:
                return Response([], status=status.HTTP_200_OK)
            queryset = queryset.filter(doctor=doctor)
        else:
            # LAB / ADMIN: optional query param filtering
            doctor_id = request.query_params.get('doctorId')
            lab_id = request.query_params.get('labId')
            if doctor_id:
                queryset = queryset.filter(doctor__code=doctor_id)
            if lab_id:
                queryset = queryset.filter(lab__code=lab_id)

        # Pagination
        try:
            page = max(1, int(request.query_params.get('page', 1)))
            page_size = min(100, max(1, int(request.query_params.get('page_size', 50))))
        except (ValueError, TypeError):
            page = 1
            page_size = 50

        total = queryset.count()
        offset = (page - 1) * page_size
        queryset = queryset[offset:offset + page_size]

        result = []
        for screening in queryset:
            patient = screening.patient
            result.append({
                'id': str(screening.id),
                'patientId': patient.patient_id if patient else None,
                'name': patient.name if patient else '',  # Decrypted via property
                'age': patient.age if patient else '',
                'sex': patient.sex if patient else '',
                'labId': screening.lab.code if screening.lab else '',
                'date': screening.created_at.strftime('%Y-%m-%d'),
                'result': screening.risk_class,
                'status': screening.status,
                'is_reviewed': screening.is_reviewed,
            })

        log_phi_access(request, '*', 'PHI_READ', {
            'view': 'CaseStatsView',
            'records_returned': len(result),
            'filters': {
                'doctorId': request.query_params.get('doctorId'),
                'labId': request.query_params.get('labId'),
                'page': page,
            },
        })

        return Response({
            'count': total,
            'page': page,
            'page_size': page_size,
            'results': result,
        })


class PatientTrendView(APIView):
    """
    Historical CBC trend for a single patient.

    GET /api/analytics/trend/<patient_id>

    Returns all screenings for the patient ordered chronologically,
    including key CBC values and risk classification.
    DOCTOR role is scoped to their own patients only.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.ADMIN, Role.LAB, Role.DOCTOR]

    def get(self, request, patient_id):
        # Cache key includes user_id so DOCTOR isolation is preserved across cache hits
        ck = _cache_key('trend', request.user.pk, patient_id)
        cached = cache.get(ck)
        if cached is not None:
            logger.debug("cache_hit", key=ck)
            return Response(cached)

        try:
            patient = Patient.objects.get(patient_id=patient_id)
        except Patient.DoesNotExist:
            return Response({'error': 'Patient not found'}, status=status.HTTP_404_NOT_FOUND)

        screenings_qs = Screening.objects.filter(patient=patient).order_by('created_at')

        if request.user.role == Role.DOCTOR:
            doctor = Doctor.objects.filter(email=request.user.email, is_active=True).first()
            if not doctor:
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)
            screenings_qs = screenings_qs.filter(doctor=doctor)

        trend = []
        for s in screenings_qs:
            cbc = s.cbc_snapshot or {}
            trend.append({
                'date': s.created_at.strftime('%Y-%m-%d'),
                'screeningId': str(s.id),
                'riskClass': s.risk_class,
                'labelText': s.label_text,
                'MCV': cbc.get('MCV'),
                'MCH': cbc.get('MCH'),
                'MCHC': cbc.get('MCHC'),
                'RBC': cbc.get('RBC'),
                'Hgb': cbc.get('Hgb'),
                'WBC': cbc.get('WBC'),
                'Platelets': cbc.get('Platelets'),
            })

        log_phi_access(request, patient_id, 'PHI_TREND', {
            'screenings_returned': len(trend),
        })

        payload = {'patientId': patient_id, 'trend': trend}
        cache.set(ck, payload, timeout=60)
        return Response(payload)


class ScreeningDetailView(APIView):
    """
    Full screening record for View Details / Download Report.

    GET /api/analytics/screening/{screening_id}

    Access rules mirror CaseStatsView:
    - DOCTOR: may only retrieve screenings linked to their own doctor record.
    - LAB / ADMIN: unrestricted within the tenant.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.ADMIN, Role.LAB, Role.DOCTOR]

    def get(self, request, screening_id):
        try:
            screening = Screening.objects.select_related(
                'patient', 'lab', 'doctor'
            ).get(id=screening_id)
        except (Screening.DoesNotExist, Exception):
            return Response({'error': 'Screening not found'}, status=status.HTTP_404_NOT_FOUND)

        # DOCTOR isolation: can only view their own patients' screenings
        if request.user.role == Role.DOCTOR:
            doctor = Doctor.objects.filter(email=request.user.email, is_active=True).first()
            if not doctor or screening.doctor_id != doctor.id:
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        log_phi_access(request, screening.patient.patient_id if screening.patient else '*',
                       'PHI_READ', {'view': 'ScreeningDetailView', 'screening_id': str(screening_id)})

        serializer = ScreeningSerializer(screening)
        return Response(serializer.data)

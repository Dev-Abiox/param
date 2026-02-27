"""
Analytics API views for dashboard and reporting.
"""

import logging
from datetime import datetime, timedelta, timezone

import structlog
from django.core.cache import cache
from django.db import connection
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth, TruncDate
from redis.exceptions import RedisError
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.audit import log_phi_access
from apps.core.models import Role
from apps.core.permissions import HasRole, IsMFAVerified
from apps.screening.ml_engine import get_ml_engine
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
    required_roles = [Role.LAB, Role.DOCTOR]

    def get(self, request):
        ck = _cache_key('summary', request.user.pk)
        try:
            cached = cache.get(ck)
        except RedisError:
            logger.warning("cache_get_failed", key=ck)
            cached = None
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
                'mcv': (s.cbc_snapshot or {}).get('MCV', '-'),
                'result': result_str,
            })

        try:
            ml_engine = get_ml_engine()
            ml_status = ml_engine.get_status()
        except Exception:
            logger.warning("ml_engine_status_failed")
            ml_status = {}
        vm = ml_status.get('validation_metrics', {})

        payload = {
            'totalCases': total_cases,
            'dailyTests': daily_tests,
            'modelMetrics': {
                'accuracy': vm.get('accuracy', 0),
                'recall': vm.get('recall', 0),
                'precision': vm.get('precision', 0),
                'f1Score': vm.get('f1_score', 0),
                'auc': vm.get('auc_roc', 0),
                'trainingLoss': vm.get('training_loss', 0),
                'validationDataset': vm.get('dataset', ''),
                'version': ml_status.get('version', 'unknown'),
            },
            'distribution': [
                {'name': 'Normal', 'value': normal_count, 'fill': '#10b981'},
                {'name': 'Borderline', 'value': borderline_count, 'fill': '#f59e0b'},
                {'name': 'Deficient', 'value': deficient_count, 'fill': '#ef4444'},
            ],
            'recentCases': recent,
        }
        try:
            cache.set(ck, payload, timeout=60)
        except RedisError:
            logger.warning("cache_set_failed", key=ck)
        return Response(payload)


class LabStatsView(APIView):
    """
    Lab-level statistics.

    GET /api/analytics/labs
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.SUPER_ADMIN]

    def get(self, request):
        ck = _cache_key('labs')
        try:
            cached = cache.get(ck)
        except RedisError:
            logger.warning("cache_get_failed", key=ck)
            cached = None
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

        try:
            cache.set(ck, result, timeout=120)
        except RedisError:
            logger.warning("cache_set_failed", key=ck)
        return Response(result)


class DoctorStatsView(APIView):
    """
    Doctor-level statistics.

    GET /api/analytics/doctors?labId=LAB-001
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB]

    def get(self, request):
        lab_id = request.query_params.get('labId', '')
        ck = _cache_key('doctors', lab_id or 'all')
        try:
            cached = cache.get(ck)
        except RedisError:
            logger.warning("cache_get_failed", key=ck)
            cached = None
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

        try:
            cache.set(ck, result, timeout=60)
        except RedisError:
            logger.warning("cache_set_failed", key=ck)
        return Response(result)


class CaseStatsView(APIView):
    """
    Case-level details with patient info.

    GET /api/analytics/cases?doctorId=D001&labId=LAB-001

    Access rules:
    - DOCTOR: always sees only their own cases; doctorId param is ignored and
              rejected with 403 if it doesn't belong to the requesting user.
    - LAB: may filter by doctorId and labId query params.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB, Role.DOCTOR]

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
            # LAB: optional query param filtering
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
    required_roles = [Role.LAB, Role.DOCTOR]

    def get(self, request, patient_id):
        # Cache key includes user_id so DOCTOR isolation is preserved across cache hits
        ck = _cache_key('trend', request.user.pk, patient_id)
        try:
            cached = cache.get(ck)
        except RedisError:
            logger.warning("cache_get_failed", key=ck)
            cached = None
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
        try:
            cache.set(ck, payload, timeout=60)
        except RedisError:
            logger.warning("cache_set_failed", key=ck)
        return Response(payload)


class ScreeningDetailView(APIView):
    """
    Full screening record for View Details / Download Report.

    GET /api/analytics/screening/{screening_id}

    Access rules mirror CaseStatsView:
    - DOCTOR: may only retrieve screenings linked to their own doctor record.
    - LAB: unrestricted within the tenant.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB, Role.DOCTOR]

    def get(self, request, screening_id):
        try:
            screening = Screening.objects.select_related(
                'patient', 'lab', 'doctor'
            ).get(id=screening_id)
        except Screening.DoesNotExist:
            return Response({'error': 'Screening not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            logger.exception("screening_detail_fetch_failed", screening_id=str(screening_id))
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


# ── Population Health Analytics ────────────────────────────────────────────────

class PopulationTrendsView(APIView):
    """
    Aggregate monthly screening trends across the tenant's patient population.

    GET /api/analytics/population/trends?months=6

    Returns a time series of risk class counts per month, showing how the
    distribution of Normal / Borderline / Deficient has shifted over time.
    SUPER_ADMIN-only — provides cross-patient aggregate data.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.SUPER_ADMIN]

    def get(self, request):
        try:
            months = min(24, max(1, int(request.query_params.get('months', 6))))
        except (ValueError, TypeError):
            months = 6

        ck = _cache_key('population_trends', months)
        try:
            cached = cache.get(ck)
            if cached is not None:
                return Response(cached)
        except RedisError:
            logger.warning("cache_get_failed", key=ck)

        since = datetime.now(timezone.utc) - timedelta(days=months * 30)
        qs = (
            Screening.objects
            .filter(created_at__gte=since)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(
                total=Count('id'),
                normal=Count('id', filter=Q(risk_class=1)),
                borderline=Count('id', filter=Q(risk_class=2)),
                deficient=Count('id', filter=Q(risk_class=3)),
            )
            .order_by('month')
        )

        payload = [
            {
                'month': row['month'].strftime('%Y-%m'),
                'total': row['total'],
                'normal': row['normal'],
                'borderline': row['borderline'],
                'deficient': row['deficient'],
                'deficient_rate': (
                    round(row['deficient'] / row['total'] * 100, 1)
                    if row['total'] > 0 else 0
                ),
            }
            for row in qs
        ]

        try:
            cache.set(ck, payload, timeout=300)
        except RedisError:
            logger.warning("cache_set_failed", key=ck)
        return Response({'months': months, 'trends': payload})


class PopulationCohortsView(APIView):
    """
    Cohort breakdown of the patient population by age group and sex.

    GET /api/analytics/population/cohorts

    Returns a matrix showing risk distribution across demographic cohorts,
    enabling identification of high-risk population segments.
    SUPER_ADMIN-only.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.SUPER_ADMIN]

    AGE_GROUPS = [
        ('pediatric', 0, 17),
        ('young_adult', 18, 39),
        ('middle_aged', 40, 59),
        ('elderly', 60, 120),
    ]

    def get(self, request):
        ck = _cache_key('population_cohorts')
        try:
            cached = cache.get(ck)
            if cached is not None:
                return Response(cached)
        except RedisError:
            logger.warning("cache_get_failed", key=ck)

        cohorts = []
        for label, age_min, age_max in self.AGE_GROUPS:
            for sex in ('M', 'F'):
                base_qs = Screening.objects.filter(
                    cbc_snapshot__Age__gte=age_min,
                    cbc_snapshot__Age__lte=age_max,
                    cbc_snapshot__Sex=sex,
                )
                total = base_qs.count()
                if total == 0:
                    continue
                deficient = base_qs.filter(risk_class=3).count()
                borderline = base_qs.filter(risk_class=2).count()
                normal = base_qs.filter(risk_class=1).count()
                cohorts.append({
                    'age_group': label,
                    'sex': sex,
                    'total': total,
                    'normal': normal,
                    'borderline': borderline,
                    'deficient': deficient,
                    'deficient_rate': round(deficient / total * 100, 1),
                })

        payload = {'cohorts': cohorts}
        try:
            cache.set(ck, payload, timeout=600)
        except RedisError:
            logger.warning("cache_set_failed", key=ck)
        return Response(payload)


class LabComparisonView(APIView):
    """
    Cross-lab screening performance comparison.

    GET /api/analytics/population/labs/compare

    Returns per-lab aggregate statistics (total screenings, deficiency rate)
    to enable benchmarking across collection sites.
    SUPER_ADMIN-only.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.SUPER_ADMIN]

    def get(self, request):
        ck = _cache_key('lab_comparison')
        try:
            cached = cache.get(ck)
            if cached is not None:
                return Response(cached)
        except RedisError:
            logger.warning("cache_get_failed", key=ck)

        labs = (
            Lab.objects
            .filter(is_active=True)
            .annotate(
                total=Count('screenings'),
                normal=Count('screenings', filter=Q(screenings__risk_class=1)),
                borderline=Count('screenings', filter=Q(screenings__risk_class=2)),
                deficient=Count('screenings', filter=Q(screenings__risk_class=3)),
            )
            .order_by('-total')
        )

        result = []
        for lab in labs:
            result.append({
                'labId': lab.code,
                'labName': lab.name,
                'total': lab.total,
                'normal': lab.normal,
                'borderline': lab.borderline,
                'deficient': lab.deficient,
                'deficient_rate': (
                    round(lab.deficient / lab.total * 100, 1)
                    if lab.total > 0 else 0
                ),
            })

        try:
            cache.set(ck, result, timeout=600)
        except RedisError:
            logger.warning("cache_set_failed", key=ck)
        return Response({'labs': result})

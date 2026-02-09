"""
Analytics API views for dashboard and reporting.
"""

import logging
from datetime import datetime, timedelta, timezone

from django.db.models import Count
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import Role
from apps.core.permissions import HasRole
from apps.screening.models import Doctor, Lab, Patient, Screening

logger = logging.getLogger(__name__)


class SummaryView(APIView):
    """
    Dashboard summary statistics.

    GET /api/analytics/summary
    For DOCTOR role: returns only their own stats filtered by doctor email.
    """
    permission_classes = [IsAuthenticated, HasRole]
    required_roles = [Role.ADMIN, Role.LAB, Role.DOCTOR]

    def get(self, request):
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

        return Response({
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
        })


class LabStatsView(APIView):
    """
    Lab-level statistics.

    GET /api/analytics/labs
    """
    permission_classes = [IsAuthenticated, HasRole]
    required_roles = [Role.ADMIN]

    def get(self, request):
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

        return Response(result)


class DoctorStatsView(APIView):
    """
    Doctor-level statistics.

    GET /api/analytics/doctors?labId=LAB-001
    """
    permission_classes = [IsAuthenticated, HasRole]
    required_roles = [Role.ADMIN, Role.LAB]

    def get(self, request):
        lab_id = request.query_params.get('labId')

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

        return Response(result)


class CaseStatsView(APIView):
    """
    Case-level details with patient info.

    GET /api/analytics/cases?doctorId=D001&labId=LAB-001
    """
    permission_classes = [IsAuthenticated, HasRole]
    required_roles = [Role.ADMIN, Role.LAB, Role.DOCTOR]

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
            })

        return Response(result)

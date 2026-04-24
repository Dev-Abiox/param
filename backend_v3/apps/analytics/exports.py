"""
Analytics data export views — CSV and PDF.

GET /api/analytics/export/csv?type=cases&labId=LAB-001&dateFrom=2025-01-01&dateTo=2025-12-31
GET /api/analytics/export/pdf/<screening_id>
"""

import csv
import io
import logging
from datetime import datetime, timezone

from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.audit import log_phi_access
from apps.core.models import Role
from apps.core.permissions import HasRole, IsMFAVerified
from apps.screening.models import Doctor, Screening

logger = logging.getLogger(__name__)


class ExportCSVView(APIView):
    """
    Export screening data as CSV.

    GET /api/analytics/export/csv

    Query params:
        type       — 'cases' (default), 'summary'
        labId      — filter by lab code
        doctorId   — filter by doctor code
        dateFrom   — ISO date (inclusive)
        dateTo     — ISO date (inclusive)
        limit      — max rows (default 5000, max 10000)
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB, Role.DOCTOR]

    def get(self, request):
        queryset = Screening.objects.select_related(
            'patient', 'lab', 'doctor',
        ).order_by('-created_at')

        # Doctor isolation
        if request.user.role == Role.DOCTOR:
            doctor = Doctor.objects.filter(email=request.user.email, is_active=True).first()
            if not doctor:
                return Response([], status=status.HTTP_200_OK)
            queryset = queryset.filter(doctor=doctor)
        else:
            lab_id = request.query_params.get('labId')
            doctor_id = request.query_params.get('doctorId')
            if lab_id:
                queryset = queryset.filter(lab__code=lab_id)
            if doctor_id:
                queryset = queryset.filter(doctor__code=doctor_id)

        # Date range
        date_from = request.query_params.get('dateFrom')
        date_to = request.query_params.get('dateTo')
        if date_from:
            try:
                queryset = queryset.filter(created_at__date__gte=date_from)
            except (ValueError, TypeError):
                pass
        if date_to:
            try:
                queryset = queryset.filter(created_at__date__lte=date_to)
            except (ValueError, TypeError):
                pass

        # Limit
        try:
            limit = min(10000, max(1, int(request.query_params.get('limit', 5000))))
        except (ValueError, TypeError):
            limit = 5000
        queryset = queryset[:limit]

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Screening ID', 'Date', 'Patient ID', 'Age', 'Sex',
            'Lab', 'Doctor', 'Risk Class', 'Label',
            'P(Normal)', 'P(Borderline)', 'P(Deficient)',
            'Hb', 'RBC', 'MCV', 'MCH', 'MCHC', 'RDW',
            'WBC', 'Platelets', 'Status', 'Reviewed',
        ])

        for s in queryset:
            cbc = s.get_cbc_dict()
            probs = s.probabilities or {}
            writer.writerow([
                str(s.id),
                s.created_at.strftime('%Y-%m-%d %H:%M'),
                s.patient.patient_id if s.patient else '',
                cbc.get('Age', ''),
                cbc.get('Sex', ''),
                s.lab.code if s.lab else '',
                s.doctor.code if s.doctor else '',
                s.risk_class,
                s.label_text,
                probs.get('normal', ''),
                probs.get('borderline', ''),
                probs.get('deficient', ''),
                cbc.get('Hb', ''),
                cbc.get('RBC', ''),
                cbc.get('MCV', ''),
                cbc.get('MCH', ''),
                cbc.get('MCHC', ''),
                cbc.get('RDW', ''),
                cbc.get('WBC', ''),
                cbc.get('Platelets', ''),
                s.status,
                'Yes' if s.is_reviewed else 'No',
            ])

        log_phi_access(request, '*', 'PHI_EXPORT_CSV', {
            'rows_exported': len(queryset) if hasattr(queryset, '__len__') else limit,
            'filters': {
                'labId': request.query_params.get('labId'),
                'doctorId': request.query_params.get('doctorId'),
                'dateFrom': date_from,
                'dateTo': date_to,
            },
        })

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')
        response['Content-Disposition'] = f'attachment; filename="clinomic_screenings_{timestamp}.csv"'
        return response


class ExportScreeningPDFView(APIView):
    """
    Export a single screening report as PDF.

    GET /api/analytics/export/pdf/<screening_id>

    Generates a clinical-style PDF report with CBC values, risk classification,
    SHAP feature importances (if available), and the clinical narrative.
    """
    permission_classes = [IsAuthenticated, IsMFAVerified, HasRole]
    required_roles = [Role.LAB, Role.DOCTOR]

    def get(self, request, screening_id):
        try:
            screening = Screening.objects.select_related(
                'patient', 'lab', 'doctor',
            ).get(id=screening_id)
        except Screening.DoesNotExist:
            return Response({'error': 'Screening not found'}, status=status.HTTP_404_NOT_FOUND)

        # Doctor isolation
        if request.user.role == Role.DOCTOR:
            doctor = Doctor.objects.filter(email=request.user.email, is_active=True).first()
            if not doctor or screening.doctor_id != doctor.id:
                return Response({'error': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        log_phi_access(request, screening.patient.patient_id if screening.patient else '*',
                       'PHI_EXPORT_PDF', {'screening_id': str(screening_id)})

        # Build a text-based PDF-like report using ReportLab if available,
        # otherwise fall back to a plain-text report delivered as PDF content-type.
        try:
            pdf_bytes = self._generate_pdf(screening)
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = (
                f'attachment; filename="screening_report_{screening.id}.pdf"'
            )
            return response
        except ImportError:
            # ReportLab not installed — return structured JSON for client-side rendering
            return Response(self._report_data(screening))

    def _report_data(self, screening) -> dict:
        """Structured report data for client-side PDF generation."""
        cbc = screening.get_cbc_dict()
        probs = screening.probabilities or {}
        indices = screening.indices or {}
        return {
            'screening_id': str(screening.id),
            'date': screening.created_at.strftime('%Y-%m-%d %H:%M UTC'),
            'patient_id': screening.patient.patient_id if screening.patient else '',
            'lab': screening.lab.name if screening.lab else '',
            'doctor': screening.doctor.name if screening.doctor else '',
            'risk_class': screening.risk_class,
            'label': screening.label_text,
            'probabilities': probs,
            'cbc_values': cbc,
            'indices': {k: v for k, v in indices.items() if k != 'shap_values'},
            'shap_features': indices.get('shap_values', {}),
            'narrative': screening.narrative,
            'model_version': screening.model_version,
            'reviewed': screening.is_reviewed,
            'clinical_note': screening.clinical_note,
            'reviewed_by': screening.reviewed_by,
        }

    def _generate_pdf(self, screening) -> bytes:
        """Generate a PDF report using ReportLab."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        from reportlab.lib.styles import getSampleStyleSheet

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
        styles = getSampleStyleSheet()
        elements = []

        # Title
        elements.append(Paragraph("Clinomic B12 Screening Report", styles['Title']))
        elements.append(Spacer(1, 6 * mm))

        # Patient info
        data = self._report_data(screening)
        info_rows = [
            ['Screening ID', data['screening_id']],
            ['Date', data['date']],
            ['Patient ID', data['patient_id']],
            ['Lab', data['lab']],
            ['Doctor', data['doctor']],
        ]
        info_table = Table(info_rows, colWidths=[120, 350])
        info_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 6 * mm))

        # Risk classification
        risk_color = {1: colors.green, 2: colors.orange, 3: colors.red}.get(
            data['risk_class'], colors.black
        )
        elements.append(Paragraph(
            f"Risk Classification: <font color='{risk_color}'><b>{data['label']}</b></font> "
            f"(Class {data['risk_class']})",
            styles['Heading2'],
        ))
        elements.append(Spacer(1, 4 * mm))

        # CBC Values table
        cbc = data['cbc_values']
        cbc_rows = [['Parameter', 'Value']]
        for param in ['Hb', 'RBC', 'HCT', 'MCV', 'MCH', 'MCHC', 'RDW', 'WBC', 'Platelets']:
            val = cbc.get(param, '-')
            cbc_rows.append([param, str(val)])

        cbc_table = Table(cbc_rows, colWidths=[120, 100])
        cbc_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ]))
        elements.append(Paragraph("CBC Parameters", styles['Heading3']))
        elements.append(cbc_table)
        elements.append(Spacer(1, 6 * mm))

        # Narrative
        if data['narrative']:
            elements.append(Paragraph("Clinical Narrative", styles['Heading3']))
            elements.append(Paragraph(data['narrative'], styles['Normal']))
            elements.append(Spacer(1, 4 * mm))

        # SHAP Features
        if data['shap_features']:
            elements.append(Paragraph("Feature Importance (SHAP)", styles['Heading3']))
            shap_rows = [['Feature', 'SHAP Value', 'Direction']]
            sorted_shap = sorted(data['shap_features'].items(), key=lambda x: abs(x[1]), reverse=True)
            for name, val in sorted_shap[:10]:
                direction = 'Risk Increasing' if val > 0 else 'Risk Decreasing'
                shap_rows.append([name, f'{val:.4f}', direction])
            shap_table = Table(shap_rows, colWidths=[120, 100, 120])
            shap_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ]))
            elements.append(shap_table)
            elements.append(Spacer(1, 4 * mm))

        # Footer
        elements.append(Spacer(1, 10 * mm))
        elements.append(Paragraph(
            f"Model Version: {data['model_version']} | "
            f"Generated by Clinomic B12 Screening Platform",
            styles['Normal'],
        ))

        doc.build(elements)
        return buf.getvalue()

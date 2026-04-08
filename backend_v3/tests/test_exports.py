"""
Tests for analytics CSV and PDF export endpoints.
"""

import uuid
from unittest.mock import MagicMock, patch

from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.analytics.exports import ExportCSVView, ExportScreeningPDFView
from apps.core.models import Role


def _make_user(role=Role.LAB, email="lab@example.com"):
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = False
    user.role = role
    user.email = email
    user.username = "testuser"
    user.pk = 1
    return user


def _make_request(path, user=None, params=None):
    factory = APIRequestFactory()
    request = factory.get(path, params or {})
    user = user or _make_user()
    force_authenticate(request, user=user)
    request.token_payload = {"mfa_verified": True}
    return request


class TestExportCSVView:

    @patch("apps.analytics.exports.log_phi_access")
    @patch("apps.analytics.exports.Screening.objects.select_related")
    @patch.object(ExportCSVView, 'throttle_classes', [])
    def test_returns_csv_with_correct_headers(self, mock_select, mock_log):
        screening = MagicMock()
        screening.id = uuid.uuid4()
        screening.created_at = MagicMock()
        screening.created_at.strftime.return_value = "2025-01-15 10:30"
        screening.patient.patient_id = "P001"
        screening.lab.code = "LAB-001"
        screening.doctor.code = "D001"
        screening.risk_class = 1
        screening.label_text = "NORMAL"
        screening.probabilities = {"normal": 0.9, "borderline": 0.07, "deficient": 0.03}
        screening.cbc_snapshot = {"Hb": 14.5, "RBC": 4.8, "MCV": 88, "MCH": 29, "MCHC": 33, "RDW": 13, "WBC": 6, "Platelets": 245, "Age": 35, "Sex": "M"}
        screening.status = "completed"
        screening.is_reviewed = True

        mock_qs = MagicMock()
        mock_qs.order_by.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.__getitem__ = MagicMock(return_value=[screening])
        mock_qs.__iter__ = MagicMock(return_value=iter([screening]))
        mock_select.return_value = mock_qs

        request = _make_request("/api/analytics/export/csv")
        response = ExportCSVView.as_view()(request)

        assert response.status_code == 200
        assert response['Content-Type'] == 'text/csv'
        assert 'clinomic_screenings_' in response['Content-Disposition']

        content = response.content.decode()
        assert 'Screening ID' in content  # header row
        assert 'P001' in content

    @patch("apps.analytics.exports.Doctor.objects.filter")
    @patch("apps.analytics.exports.Screening.objects.select_related")
    @patch.object(ExportCSVView, 'throttle_classes', [])
    def test_doctor_sees_only_own_data(self, mock_select, mock_doc_filter):
        doctor = MagicMock()
        doctor.id = uuid.uuid4()
        mock_doc_filter.return_value.first.return_value = doctor

        mock_qs = MagicMock()
        mock_qs.order_by.return_value = mock_qs
        mock_qs.filter.return_value = mock_qs
        mock_qs.__getitem__ = MagicMock(return_value=[])
        mock_qs.__iter__ = MagicMock(return_value=iter([]))
        mock_select.return_value = mock_qs

        user = _make_user(role=Role.DOCTOR, email="doc@example.com")
        request = _make_request("/api/analytics/export/csv", user=user)

        with patch("apps.analytics.exports.log_phi_access"):
            response = ExportCSVView.as_view()(request)

        assert response.status_code == 200
        # Verify filter was called with doctor
        mock_qs.filter.assert_called_with(doctor=doctor)


class TestExportScreeningPDFView:

    @patch("apps.analytics.exports.log_phi_access")
    @patch("apps.analytics.exports.Screening.objects.select_related")
    @patch.object(ExportScreeningPDFView, 'throttle_classes', [])
    def test_returns_report_data_when_reportlab_missing(self, mock_select, mock_log):
        screening = MagicMock()
        screening.id = uuid.uuid4()
        screening.created_at.strftime.return_value = "2025-01-15 10:30 UTC"
        screening.patient.patient_id = "P001"
        screening.lab.name = "Lab Alpha"
        screening.doctor.name = "Dr Smith"
        screening.doctor_id = None
        screening.risk_class = 3
        screening.label_text = "DEFICIENT"
        screening.probabilities = {"normal": 0.1, "borderline": 0.2, "deficient": 0.7}
        screening.cbc_snapshot = {"Hb": 9.8, "MCV": 108}
        screening.indices = {"mentzer": 15.0}
        screening.narrative = "High risk detected."
        screening.model_version = "1.0.0"
        screening.is_reviewed = False
        screening.clinical_note = ""
        screening.reviewed_by = ""

        mock_select.return_value.get.return_value = screening

        sid = uuid.uuid4()
        request = _make_request(f"/api/analytics/export/pdf/{sid}")

        # Patch _generate_pdf to raise ImportError (simulate no reportlab)
        with patch.object(ExportScreeningPDFView, '_generate_pdf', side_effect=ImportError):
            response = ExportScreeningPDFView.as_view()(request, screening_id=sid)

        assert response.status_code == 200
        assert response.data['screening_id'] == str(screening.id)
        assert response.data['label'] == 'DEFICIENT'
        assert response.data['narrative'] == 'High risk detected.'

    @patch("apps.analytics.exports.Screening.objects.select_related")
    @patch.object(ExportScreeningPDFView, 'throttle_classes', [])
    def test_screening_not_found_returns_404(self, mock_select):
        from apps.screening.models import Screening
        mock_select.return_value.get.side_effect = Screening.DoesNotExist

        sid = uuid.uuid4()
        request = _make_request(f"/api/analytics/export/pdf/{sid}")
        response = ExportScreeningPDFView.as_view()(request, screening_id=sid)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("apps.analytics.exports.Doctor.objects.filter")
    @patch("apps.analytics.exports.Screening.objects.select_related")
    @patch.object(ExportScreeningPDFView, 'throttle_classes', [])
    def test_doctor_isolation_on_pdf(self, mock_select, mock_doc_filter):
        doctor = MagicMock()
        doctor.id = uuid.uuid4()
        mock_doc_filter.return_value.first.return_value = doctor

        screening = MagicMock()
        screening.doctor_id = uuid.uuid4()  # different doctor
        mock_select.return_value.get.return_value = screening

        user = _make_user(role=Role.DOCTOR, email="doc@example.com")
        sid = uuid.uuid4()
        request = _make_request(f"/api/analytics/export/pdf/{sid}", user=user)
        response = ExportScreeningPDFView.as_view()(request, screening_id=sid)

        assert response.status_code == status.HTTP_403_FORBIDDEN

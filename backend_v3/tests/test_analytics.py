"""
Tests for analytics views: SummaryView, LabStatsView, DoctorStatsView,
CaseStatsView, PatientTrendView, ScreeningDetailView.

Covers:
  - Role-based access control
  - DOCTOR isolation (cannot see other doctors' data)
  - Cache hits (response returned without hitting DB)
  - Correct HTTP status codes
"""

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.analytics.views import (
    CaseStatsView,
    DoctorStatsView,
    LabStatsView,
    PatientTrendView,
    ScreeningDetailView,
    SummaryView,
)
from apps.core.models import Role


def _make_user(role=Role.LAB, email="lab@example.com", pk=1):
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = False
    user.role = role
    user.email = email
    user.pk = pk
    return user


def _get(path, user, params=None):
    factory = APIRequestFactory()
    request = factory.get(path, params or {})
    force_authenticate(request, user=user)
    request.token_payload = {"mfa_verified": True}
    return request


# ── SummaryView ────────────────────────────────────────────────────────────────

class TestSummaryView:

    @patch("apps.analytics.views.cache")
    @patch("apps.analytics.views.Screening.objects.all")
    def test_cache_hit_skips_db(self, mock_all, mock_cache):
        mock_cache.get.return_value = {"totalCases": 5, "cached": True}
        user = _make_user(role=Role.ADMIN)
        response = SummaryView.as_view()(_get("/api/analytics/summary", user))
        assert response.status_code == status.HTTP_200_OK
        assert response.data.get("cached") is True
        mock_all.assert_not_called()  # DB not hit on cache hit

    @patch("apps.analytics.views.cache")
    @patch("apps.analytics.views.Screening.objects.all")
    def test_cache_miss_hits_db_and_sets_cache(self, mock_all, mock_cache):
        mock_cache.get.return_value = None  # cache miss

        qs = MagicMock()
        qs.count.return_value = 10
        qs.filter.return_value.count.return_value = 5
        qs.select_related.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        mock_all.return_value = qs

        user = _make_user(role=Role.ADMIN)
        response = SummaryView.as_view()(_get("/api/analytics/summary", user))
        assert response.status_code == status.HTTP_200_OK
        mock_cache.set.assert_called_once()

    def test_unauthenticated_denied(self):
        user = MagicMock(is_authenticated=False)
        request = _get("/api/analytics/summary", user)
        response = SummaryView.as_view()(request)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


# ── LabStatsView ───────────────────────────────────────────────────────────────

class TestLabStatsView:

    @patch("apps.analytics.views.cache")
    @patch("apps.analytics.views.Lab.objects.filter")
    def test_admin_sees_labs(self, mock_filter, mock_cache):
        mock_cache.get.return_value = None
        lab = MagicMock()
        lab.id = "00000000-0000-0000-0000-000000000001"
        lab.code, lab.name, lab.tier = "LAB-001", "Test Lab", "standard"
        lab.doctors_count, lab.cases_count = 3, 10
        mock_filter.return_value.annotate.return_value = [lab]

        user = _make_user(role=Role.ADMIN)
        response = LabStatsView.as_view()(_get("/api/analytics/labs", user))
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1

    def test_lab_role_denied(self):
        user = _make_user(role=Role.LAB)
        request = _get("/api/analytics/labs", user)
        response = LabStatsView.as_view()(request)
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ── DoctorStatsView ────────────────────────────────────────────────────────────

class TestDoctorStatsView:

    @patch("apps.analytics.views.cache")
    @patch("apps.analytics.views.Doctor.objects.filter")
    def test_lab_role_can_see_doctors(self, mock_filter, mock_cache):
        mock_cache.get.return_value = None
        doc = MagicMock()
        doc.id = "00000000-0000-0000-0000-000000000002"
        doc.code, doc.name, doc.department, doc.cases_count = "D001", "Dr. X", "Hematology", 5
        mock_filter.return_value.annotate.return_value.select_related.return_value = [doc]

        user = _make_user(role=Role.LAB)
        response = DoctorStatsView.as_view()(_get("/api/analytics/doctors", user))
        assert response.status_code == status.HTTP_200_OK

    def test_doctor_role_denied(self):
        user = _make_user(role=Role.DOCTOR)
        request = _get("/api/analytics/doctors", user)
        response = DoctorStatsView.as_view()(request)
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ── CaseStatsView (DOCTOR isolation) ──────────────────────────────────────────

class TestCaseStatsViewIsolation:
    """Re-runs the doctor isolation tests through analytics module."""

    @patch("apps.analytics.views.Doctor.objects.filter")
    @patch("apps.analytics.views.Screening.objects.select_related")
    def test_doctor_blocked_from_passing_doctorId(self, mock_sel, mock_doc_filter):
        user = _make_user(role=Role.DOCTOR, pk=10)
        request = _get("/api/analytics/cases", user, params={"doctorId": "D999"})
        response = CaseStatsView.as_view()(request)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("apps.analytics.views.cache")
    @patch("apps.analytics.views.Doctor.objects.filter")
    @patch("apps.analytics.views.Screening.objects.select_related")
    def test_doctor_with_no_record_returns_empty(self, mock_sel, mock_doc_filter, mock_cache):
        mock_cache.get.return_value = None
        mock_doc_filter.return_value.first.return_value = None

        user = _make_user(role=Role.DOCTOR, pk=11)
        response = CaseStatsView.as_view()(_get("/api/analytics/cases", user))
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []


# ── PatientTrendView ───────────────────────────────────────────────────────────

class TestPatientTrendView:

    @patch("apps.analytics.views.cache")
    @patch("apps.analytics.views.Patient.objects.get")
    def test_patient_not_found_returns_404(self, mock_get, mock_cache):
        from apps.screening.models import Patient
        mock_cache.get.return_value = None
        mock_get.side_effect = Patient.DoesNotExist

        user = _make_user(role=Role.ADMIN)
        response = PatientTrendView.as_view()(_get("/api/analytics/trend/UNKNOWN", user), patient_id="UNKNOWN")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("apps.analytics.views.cache")
    @patch("apps.analytics.views.Screening.objects.filter")
    @patch("apps.analytics.views.Patient.objects.get")
    def test_doctor_scoped_to_own_patients(self, mock_patient_get, mock_screening_filter, mock_cache):
        mock_cache.get.return_value = None

        patient = MagicMock()
        mock_patient_get.return_value = patient

        qs = MagicMock()
        qs.filter.return_value = qs
        qs.order_by.return_value = []
        mock_screening_filter.return_value = qs

        # Doctor with no matching record → 403
        with patch("apps.analytics.views.Doctor.objects.filter") as mock_doc:
            mock_doc.return_value.first.return_value = None
            user = _make_user(role=Role.DOCTOR, pk=20)
            response = PatientTrendView.as_view()(
                _get("/api/analytics/trend/P001", user),
                patient_id="P001",
            )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ── ScreeningDetailView ────────────────────────────────────────────────────────

class TestScreeningDetailView:

    @patch("apps.analytics.views.Screening.objects.select_related")
    def test_screening_not_found_returns_404(self, mock_sel):
        from apps.screening.models import Screening
        mock_sel.return_value.get.side_effect = Screening.DoesNotExist

        import uuid
        sid = uuid.uuid4()
        user = _make_user(role=Role.ADMIN)
        response = ScreeningDetailView.as_view()(
            _get(f"/api/analytics/screening/{sid}", user),
            screening_id=sid,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("apps.analytics.views.log_phi_access")
    @patch("apps.analytics.views.ScreeningSerializer")
    @patch("apps.analytics.views.Screening.objects.select_related")
    def test_admin_can_view_any_screening(self, mock_sel, mock_ser, mock_log):
        import uuid
        sid = uuid.uuid4()

        screening = MagicMock()
        screening.patient.patient_id = "P001"
        mock_sel.return_value.get.return_value = screening

        mock_ser_instance = MagicMock()
        mock_ser_instance.data = {"id": str(sid)}
        mock_ser.return_value = mock_ser_instance

        user = _make_user(role=Role.ADMIN)
        response = ScreeningDetailView.as_view()(
            _get(f"/api/analytics/screening/{sid}", user),
            screening_id=sid,
        )
        assert response.status_code == status.HTTP_200_OK

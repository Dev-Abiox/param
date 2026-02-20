"""
Tests for the screening predict endpoint, work queue, and review workflow.
"""

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory

from apps.core.models import Role
from apps.screening.models import ScreeningStatus
from apps.screening.views import (
    CaseListView,
    ConsentRevokeView,
    PredictView,
    ReviewScreeningView,
    ScreeningStatusView,
    WorkQueueView,
)


def _make_user(role=Role.LAB, email="lab@example.com", username="lab_user"):
    user = MagicMock()
    user.is_authenticated = True
    user.role = role
    user.email = email
    user.username = username
    user.pk = 1
    return user


def _make_request(method, path, data=None, user=None, params=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    kwargs = {"format": "json"} if data is not None else {}
    request = fn(path, data, **kwargs) if data is not None else fn(path, params or {})
    request.user = user or _make_user()
    request.token_payload = {"mfa_verified": True}
    return request


# ── PredictView ────────────────────────────────────────────────────────────────

class TestPredictView:

    VALID_PAYLOAD = {
        "patientId": "P001",
        "patientName": "Test Patient",
        "labId": "LAB-001",
        "doctorId": "",
        "consentId": None,
        "cbc": {
            "Hb_g_dL": 14.5,
            "RBC_million_uL": 5.0,
            "HCT_percent": 43.5,
            "MCV_fL": 87.0,
            "MCH_pg": 29.5,
            "MCHC_g_dL": 33.5,
            "RDW_percent": 13.2,
            "WBC_10_3_uL": 6.8,
            "Platelets_10_3_uL": 245.0,
            "Neutrophils_percent": 58.0,
            "Lymphocytes_percent": 32.0,
            "Age": 45,
            "Sex": "M",
        },
    }

    def test_missing_patient_id_returns_400(self):
        payload = {**self.VALID_PAYLOAD, "patientId": ""}
        request = _make_request("post", "/api/screening/predict", payload)
        response = PredictView.as_view()(request)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.screening.views.NarrativeEngine")
    @patch("apps.screening.views.Screening.objects.create")
    @patch("apps.screening.views.Patient.objects.update_or_create")
    @patch("apps.screening.views.Lab.objects.filter")
    @patch("apps.screening.views.Doctor.objects.filter")
    @patch("apps.screening.views.get_ml_engine")
    def test_valid_predict_returns_200(
        self, mock_engine, mock_doctor, mock_lab, mock_patient_uoc, mock_screening_create, mock_narrative_cls
    ):
        # Mock ML engine
        engine = MagicMock()
        engine.predict.return_value = {
            "riskClass": 1,
            "labelText": "Normal",
            "probabilities": {"normal": 0.9, "borderline": 0.07, "deficient": 0.03},
            "rulesFired": [],
            "indices": {},
            "modelVersion": "v1.0.0",
            "modelArtifactHash": "a" * 64,
        }
        mock_engine.return_value = engine

        # Mock narrative engine
        mock_narrative = MagicMock()
        mock_narrative.generate.return_value = "Normal CBC parameters. No B12 workup needed."
        mock_narrative_cls.return_value = mock_narrative

        lab_mock = MagicMock()
        lab_mock.code = "LAB-001"
        mock_lab.return_value.first.return_value = lab_mock
        mock_doctor.return_value.first.return_value = None

        patient_mock = MagicMock()
        mock_patient_uoc.return_value = (patient_mock, True)

        screening_mock = MagicMock()
        screening_mock.id = "00000000-0000-0000-0000-000000000001"
        mock_screening_create.return_value = screening_mock

        with patch("apps.screening.views.log_phi_access"):
            request = _make_request("post", "/api/screening/predict", self.VALID_PAYLOAD)
            response = PredictView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert "label" in response.data
        assert response.data["label"] == 1
        assert "narrative" in response.data
        assert response.data["narrative"] != ''

    def test_unauthenticated_returns_403(self):
        user = MagicMock()
        user.is_authenticated = False
        request = _make_request("post", "/api/screening/predict", self.VALID_PAYLOAD, user=user)
        request.token_payload = {}
        response = PredictView.as_view()(request)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


# ── CaseListView ───────────────────────────────────────────────────────────────

class TestCaseListView:
    """Regression tests for CaseListView filter-before-slice ordering."""

    @patch("apps.screening.views.Screening.objects.select_related")
    def test_filter_applied_before_slice(self, mock_select):
        """
        Filters must be applied to the unsliced queryset.
        Before the fix, [:500] was applied first, making subsequent .filter()
        calls raise TypeError (cannot filter a sliced queryset).
        """
        ordered_qs = MagicMock(name="ordered_qs")
        ordered_qs.filter.return_value = ordered_qs
        ordered_qs.__getitem__ = MagicMock(name="slice", return_value=iter([]))
        mock_select.return_value.order_by.return_value = ordered_qs

        user = _make_user(role=Role.ADMIN)
        request = _make_request("get", "/api/screening/cases", params={"doctorId": "D001"}, user=user)
        response = CaseListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        # filter() must have been called with the doctor code
        ordered_qs.filter.assert_called_once_with(doctor__code="D001")
        # slice must have been applied (to the post-filter queryset)
        ordered_qs.__getitem__.assert_called_once()

    @patch("apps.screening.views.Screening.objects.select_related")
    def test_lab_filter_applied_before_slice(self, mock_select):
        ordered_qs = MagicMock(name="ordered_qs")
        ordered_qs.filter.return_value = ordered_qs
        ordered_qs.__getitem__ = MagicMock(name="slice", return_value=iter([]))
        mock_select.return_value.order_by.return_value = ordered_qs

        user = _make_user(role=Role.ADMIN)
        request = _make_request("get", "/api/screening/cases", params={"labId": "LAB-001"}, user=user)
        response = CaseListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        ordered_qs.filter.assert_called_once_with(lab__code="LAB-001")
        ordered_qs.__getitem__.assert_called_once()

    @patch("apps.screening.views.Screening.objects.select_related")
    def test_no_filters_still_slices(self, mock_select):
        ordered_qs = MagicMock(name="ordered_qs")
        ordered_qs.filter.return_value = ordered_qs
        ordered_qs.__getitem__ = MagicMock(name="slice", return_value=iter([]))
        mock_select.return_value.order_by.return_value = ordered_qs

        user = _make_user(role=Role.ADMIN)
        request = _make_request("get", "/api/screening/cases", user=user)
        response = CaseListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        ordered_qs.filter.assert_not_called()
        ordered_qs.__getitem__.assert_called_once()


# ── WorkQueueView ──────────────────────────────────────────────────────────────

class TestWorkQueueView:

    @patch("apps.screening.views.Screening.objects.all")
    def test_invalid_status_returns_400(self, mock_qs):
        request = _make_request("get", "/api/screening/queue", params={"status": "invalid"})
        response = WorkQueueView.as_view()(request)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.screening.views.Screening.objects.all")
    def test_pending_status_returns_200(self, mock_all):
        base_qs = MagicMock()
        base_qs.filter.return_value.count.return_value = 5
        base_qs.filter.return_value.select_related.return_value.order_by.return_value.__getitem__ = MagicMock(return_value=[])
        mock_all.return_value = base_qs

        request = _make_request("get", "/api/screening/queue", params={"status": "pending"})
        response = WorkQueueView.as_view()(request)
        assert response.status_code == status.HTTP_200_OK
        assert "counts" in response.data
        assert "items" in response.data

    def test_doctor_role_cannot_access_work_queue(self):
        user = _make_user(role=Role.DOCTOR)
        request = _make_request("get", "/api/screening/queue", user=user)
        response = WorkQueueView.as_view()(request)
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ── ScreeningStatusView ────────────────────────────────────────────────────────

class TestScreeningStatusView:

    @patch("apps.screening.views.Screening.objects.get")
    def test_invalid_transition_returns_400(self, mock_get):
        screening = MagicMock()
        screening.status = ScreeningStatus.COMPLETED
        mock_get.return_value = screening

        import uuid
        sid = uuid.uuid4()
        request = _make_request("patch", f"/api/screening/cases/{sid}/status", {"status": "pending"})
        response = ScreeningStatusView.as_view()(request, screening_id=sid)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.screening.views.Screening.objects.get")
    def test_valid_transition_returns_200(self, mock_get):
        screening = MagicMock()
        screening.id = "00000000-0000-0000-0000-000000000001"
        screening.status = ScreeningStatus.PENDING
        mock_get.return_value = screening

        import uuid
        sid = uuid.uuid4()
        request = _make_request("patch", f"/api/screening/cases/{sid}/status", {"status": "in_progress"})
        response = ScreeningStatusView.as_view()(request, screening_id=sid)
        assert response.status_code == status.HTTP_200_OK


# ── ReviewScreeningView ────────────────────────────────────────────────────────

class TestReviewScreeningView:

    @patch("apps.screening.views.Doctor.objects.filter")
    @patch("apps.screening.views.Screening.objects.select_related")
    def test_doctor_cannot_review_other_doctors_screening(self, mock_select, mock_doc_filter):
        doctor_a = MagicMock()
        doctor_a.id = "aaaa"
        mock_doc_filter.return_value.first.return_value = doctor_a

        screening = MagicMock()
        screening.doctor_id = "bbbb"  # belongs to doctor B
        mock_select.return_value.get.return_value = screening

        import uuid
        sid = uuid.uuid4()
        user = _make_user(role=Role.DOCTOR)
        request = _make_request("patch", f"/api/screening/cases/{sid}/review", {"clinical_note": "ok"}, user=user)
        response = ReviewScreeningView.as_view()(request, screening_id=sid)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("apps.screening.views.log_phi_access")
    @patch("apps.screening.views.Doctor.objects.filter")
    @patch("apps.screening.views.Screening.objects.select_related")
    def test_doctor_can_review_own_screening(self, mock_select, mock_doc_filter, mock_log):
        import uuid
        doctor_id = str(uuid.uuid4())

        doctor = MagicMock()
        doctor.id = doctor_id
        mock_doc_filter.return_value.first.return_value = doctor

        screening = MagicMock()
        screening.id = uuid.uuid4()
        screening.doctor_id = doctor_id
        screening.patient.patient_id = "P001"
        screening.reviewed_at.isoformat.return_value = "2025-01-01T00:00:00+00:00"
        mock_select.return_value.get.return_value = screening

        user = _make_user(role=Role.DOCTOR)
        request = _make_request(
            "patch", f"/api/screening/cases/{screening.id}/review",
            {"clinical_note": "Patient followed up."}, user=user
        )
        response = ReviewScreeningView.as_view()(request, screening_id=screening.id)
        assert response.status_code == status.HTTP_200_OK


# ── ConsentRevokeView ──────────────────────────────────────────────────────────

class TestConsentRevokeView:

    def _consent_id(self):
        import uuid
        return uuid.uuid4()

    @patch("apps.screening.views.Consent.objects.select_related")
    def test_admin_can_revoke_any_consent(self, mock_qs):
        consent = MagicMock()
        mock_qs.return_value.get.return_value = consent

        user = _make_user(role=Role.ADMIN)
        cid = self._consent_id()
        request = _make_request("post", f"/api/screening/consent/revoke/{cid}", user=user)
        response = ConsentRevokeView.as_view()(request, consent_id=cid)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {'status': 'revoked'}

    @patch("apps.screening.views.Consent.objects.select_related")
    def test_lab_can_revoke_any_consent(self, mock_qs):
        consent = MagicMock()
        mock_qs.return_value.get.return_value = consent

        user = _make_user(role=Role.LAB)
        cid = self._consent_id()
        request = _make_request("post", f"/api/screening/consent/revoke/{cid}", user=user)
        response = ConsentRevokeView.as_view()(request, consent_id=cid)

        assert response.status_code == status.HTTP_200_OK

    @patch("apps.screening.views.Doctor.objects.filter")
    @patch("apps.screening.views.Consent.objects.select_related")
    def test_doctor_can_revoke_own_patients_consent(self, mock_qs, mock_doc_filter):
        import uuid
        doctor_id = str(uuid.uuid4())

        doctor = MagicMock()
        doctor.id = doctor_id
        mock_doc_filter.return_value.first.return_value = doctor

        consent = MagicMock()
        consent.patient.referring_doctor_id = doctor_id
        mock_qs.return_value.get.return_value = consent

        user = _make_user(role=Role.DOCTOR)
        cid = self._consent_id()
        request = _make_request("post", f"/api/screening/consent/revoke/{cid}", user=user)
        response = ConsentRevokeView.as_view()(request, consent_id=cid)

        assert response.status_code == status.HTTP_200_OK

    @patch("apps.screening.views.Doctor.objects.filter")
    @patch("apps.screening.views.Consent.objects.select_related")
    def test_doctor_cannot_revoke_other_patients_consent(self, mock_qs, mock_doc_filter):
        import uuid
        doctor = MagicMock()
        doctor.id = str(uuid.uuid4())
        mock_doc_filter.return_value.first.return_value = doctor

        consent = MagicMock()
        consent.patient.referring_doctor_id = str(uuid.uuid4())  # different doctor
        mock_qs.return_value.get.return_value = consent

        user = _make_user(role=Role.DOCTOR)
        cid = self._consent_id()
        request = _make_request("post", f"/api/screening/consent/revoke/{cid}", user=user)
        response = ConsentRevokeView.as_view()(request, consent_id=cid)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("apps.screening.views.Doctor.objects.filter")
    @patch("apps.screening.views.Consent.objects.select_related")
    def test_doctor_with_no_doctor_record_gets_403(self, mock_qs, mock_doc_filter):
        mock_doc_filter.return_value.first.return_value = None
        consent = MagicMock()
        mock_qs.return_value.get.return_value = consent

        user = _make_user(role=Role.DOCTOR)
        cid = self._consent_id()
        request = _make_request("post", f"/api/screening/consent/revoke/{cid}", user=user)
        response = ConsentRevokeView.as_view()(request, consent_id=cid)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("apps.screening.views.Consent.objects.select_related")
    def test_missing_consent_returns_404(self, mock_qs):
        from apps.screening.models import Consent
        mock_qs.return_value.get.side_effect = Consent.DoesNotExist

        user = _make_user(role=Role.ADMIN)
        cid = self._consent_id()
        request = _make_request("post", f"/api/screening/consent/revoke/{cid}", user=user)
        response = ConsentRevokeView.as_view()(request, consent_id=cid)

        assert response.status_code == status.HTTP_404_NOT_FOUND

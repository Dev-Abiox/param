"""
Tests for SHAP explainability endpoint.

Note: v1 CatBoost engine does not compute SHAP values inline.
The ExplainView reads shap_values from stored screening.indices if present.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.models import Role
from apps.screening.views import ExplainView


def _make_user(role=Role.LAB, email="lab@example.com", username="lab_user"):
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = False
    user.role = role
    user.email = email
    user.username = username
    user.pk = 1
    return user


def _make_request(method, path, data=None, user=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    kwargs = {"format": "json"} if data is not None else {}
    request = fn(path, data, **kwargs) if data is not None else fn(path)
    user = user or _make_user()
    force_authenticate(request, user=user)
    request.token_payload = {"mfa_verified": True}
    return request


# ── ExplainView ───────────────────────────────────────────────────────────────

class TestExplainView:

    @patch("apps.screening.views.log_phi_access")
    @patch("apps.screening.views.Screening.objects.select_related")
    @patch.object(ExplainView, 'throttle_classes', [])
    def test_returns_ranked_shap_values(self, mock_select, mock_log):
        screening = MagicMock()
        screening.id = uuid.uuid4()
        screening.risk_class = 3
        screening.label_text = "DEFICIENT"
        screening.patient.patient_id = "P001"
        screening.doctor_id = None
        screening.indices = {
            'mentzer': 15.0,
            'shap_values': {
                'MCV': 0.35, 'RDW': 0.25, 'Hb': -0.15, 'Age': 0.05,
                'RBC': -0.02, 'WBC': 0.01,
            }
        }
        mock_select.return_value.get.return_value = screening

        sid = uuid.uuid4()
        request = _make_request("get", f"/api/screening/cases/{sid}/explain")
        response = ExplainView.as_view()(request, screening_id=sid)

        assert response.status_code == status.HTTP_200_OK
        features = response.data['features']
        # Should be sorted by absolute SHAP value descending
        assert features[0]['feature'] == 'MCV'  # |0.35| is highest
        assert features[0]['direction'] == 'risk_increasing'
        assert features[1]['feature'] == 'RDW'
        assert features[2]['feature'] == 'Hb'
        assert features[2]['direction'] == 'risk_decreasing'

    @patch("apps.screening.views.Screening.objects.select_related")
    @patch.object(ExplainView, 'throttle_classes', [])
    def test_no_shap_returns_404(self, mock_select):
        screening = MagicMock()
        screening.indices = {'mentzer': 15.0}  # No shap_values key
        screening.doctor_id = None
        mock_select.return_value.get.return_value = screening

        sid = uuid.uuid4()
        request = _make_request("get", f"/api/screening/cases/{sid}/explain")
        response = ExplainView.as_view()(request, screening_id=sid)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("apps.screening.views.Screening.objects.select_related")
    @patch.object(ExplainView, 'throttle_classes', [])
    def test_empty_shap_returns_404(self, mock_select):
        screening = MagicMock()
        screening.indices = {'shap_values': {}}  # Empty dict
        screening.doctor_id = None
        mock_select.return_value.get.return_value = screening

        sid = uuid.uuid4()
        request = _make_request("get", f"/api/screening/cases/{sid}/explain")
        response = ExplainView.as_view()(request, screening_id=sid)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("apps.screening.views.Screening.objects.select_related")
    @patch.object(ExplainView, 'throttle_classes', [])
    def test_screening_not_found_returns_404(self, mock_select):
        from apps.screening.models import Screening
        mock_select.return_value.get.side_effect = Screening.DoesNotExist

        sid = uuid.uuid4()
        request = _make_request("get", f"/api/screening/cases/{sid}/explain")
        response = ExplainView.as_view()(request, screening_id=sid)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch("apps.screening.views.Doctor.objects.filter")
    @patch("apps.screening.views.Screening.objects.select_related")
    @patch.object(ExplainView, 'throttle_classes', [])
    def test_doctor_isolation_enforced(self, mock_select, mock_doc_filter):
        doctor = MagicMock()
        doctor.id = uuid.uuid4()
        mock_doc_filter.return_value.first.return_value = doctor

        screening = MagicMock()
        screening.doctor_id = uuid.uuid4()  # Different doctor
        screening.indices = {'shap_values': {'MCV': 0.3}}
        mock_select.return_value.get.return_value = screening

        user = _make_user(role=Role.DOCTOR, email="doc@example.com")
        sid = uuid.uuid4()
        request = _make_request("get", f"/api/screening/cases/{sid}/explain", user=user)
        response = ExplainView.as_view()(request, screening_id=sid)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch("apps.screening.views.log_phi_access")
    @patch("apps.screening.views.Doctor.objects.filter")
    @patch("apps.screening.views.Screening.objects.select_related")
    @patch.object(ExplainView, 'throttle_classes', [])
    def test_doctor_can_access_own_screening(self, mock_select, mock_doc_filter, mock_log):
        doctor_id = uuid.uuid4()
        doctor = MagicMock()
        doctor.id = doctor_id
        mock_doc_filter.return_value.first.return_value = doctor

        screening = MagicMock()
        screening.id = uuid.uuid4()
        screening.doctor_id = doctor_id  # Same doctor
        screening.risk_class = 2
        screening.label_text = "BORDERLINE"
        screening.patient.patient_id = "P001"
        screening.indices = {'shap_values': {'MCV': 0.2, 'Hb': -0.1}}
        mock_select.return_value.get.return_value = screening

        user = _make_user(role=Role.DOCTOR, email="doc@example.com")
        sid = uuid.uuid4()
        request = _make_request("get", f"/api/screening/cases/{sid}/explain", user=user)
        response = ExplainView.as_view()(request, screening_id=sid)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['features']) == 2

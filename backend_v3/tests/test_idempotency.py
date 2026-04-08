"""
Tests for prediction idempotency (duplicate submission prevention).
"""

from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.models import Role
from apps.screening.views import PredictView


def _make_user(role=Role.LAB, email="lab@example.com", username="lab_user"):
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = False
    user.role = role
    user.email = email
    user.username = username
    user.pk = 1
    return user


def _make_request(data, user=None):
    factory = APIRequestFactory()
    request = factory.post("/api/screening/predict", data, format="json")
    user = user or _make_user()
    force_authenticate(request, user=user)
    request.token_payload = {"mfa_verified": True}
    return request


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


class TestPredictIdempotency:

    @patch("apps.screening.views.cache")
    @patch("apps.screening.views.NarrativeEngine")
    @patch("apps.screening.views.Screening.objects.create")
    @patch("apps.screening.views.Patient.objects.update_or_create")
    @patch("apps.screening.views.Lab.objects.filter")
    @patch("apps.screening.views.Doctor.objects.filter")
    @patch("apps.screening.views.get_ml_engine")
    def test_first_submission_stores_idempotency_key(
        self, mock_engine, mock_doctor, mock_lab, mock_patient_uoc,
        mock_screening_create, mock_narrative_cls, mock_cache,
    ):
        """First submission should store the screening ID in cache."""
        engine = MagicMock()
        engine.predict.return_value = {
            "riskClass": 1, "labelText": "Normal",
            "probabilities": {"normal": 0.9, "borderline": 0.07, "deficient": 0.03},
            "rulesFired": [], "indices": {}, "modelVersion": "v1.0.0",
            "modelArtifactHash": "a" * 64,
        }
        mock_engine.return_value = engine
        mock_narrative = MagicMock()
        mock_narrative.generate.return_value = "Normal."
        mock_narrative_cls.return_value = mock_narrative

        lab_mock = MagicMock()
        lab_mock.code = "LAB-001"
        mock_lab.return_value.first.return_value = lab_mock
        mock_doctor.return_value.first.return_value = None

        patient_mock = MagicMock()
        mock_patient_uoc.return_value = (patient_mock, True)

        screening_mock = MagicMock()
        screening_mock.id = "00000000-0000-0000-0000-000000000001"
        screening_mock.risk_class = 1
        mock_screening_create.return_value = screening_mock

        # Cache miss (no existing screening)
        mock_cache.get.return_value = None

        with patch("apps.screening.views.log_phi_access"), \
             patch("apps.analytics.cache.invalidate_analytics_caches"):
            request = _make_request(VALID_PAYLOAD)
            response = PredictView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        # Verify cache.set was called with the idempotency key
        cache_set_calls = [c for c in mock_cache.set.call_args_list
                           if "screening:idemp:" in str(c)]
        assert len(cache_set_calls) == 1
        args, kwargs = cache_set_calls[0]
        assert args[0].startswith("screening:idemp:")
        assert args[1] == str(screening_mock.id)
        assert kwargs.get("timeout") == 300

    @patch("apps.screening.views.cache")
    @patch("apps.screening.views.Screening.objects.filter")
    def test_duplicate_submission_returns_cached_result(
        self, mock_screening_filter, mock_cache,
    ):
        """Second identical submission should return the cached screening."""
        existing_screening = MagicMock()
        existing_screening.id = "00000000-0000-0000-0000-000000000001"
        existing_screening.risk_class = 1
        existing_screening.label_text = "Normal"
        existing_screening.probabilities = {"normal": 0.9, "borderline": 0.07, "deficient": 0.03}
        existing_screening.indices = {}
        existing_screening.rules_fired = []
        existing_screening.model_version = "v1.0.0"
        existing_screening.narrative = "Normal."

        # Cache hit
        mock_cache.get.return_value = str(existing_screening.id)
        mock_screening_filter.return_value.select_related.return_value.first.return_value = existing_screening

        request = _make_request(VALID_PAYLOAD)
        response = PredictView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["duplicate"] is True
        assert response.data["id"] == str(existing_screening.id)

    @patch("apps.screening.views.cache")
    def test_cache_failure_does_not_block_prediction(self, mock_cache):
        """If Redis is down, the idempotency check should be skipped gracefully."""
        mock_cache.get.side_effect = Exception("Redis connection failed")

        # The request should still proceed to the ML prediction path
        # (it will fail on other mocks, but should NOT fail on cache)
        request = _make_request(VALID_PAYLOAD)

        # We just verify it gets past the cache check — the serializer
        # will validate, and we'll get to the lab lookup (which returns 400
        # since lab is not mocked). That proves cache failure was handled.
        with patch("apps.screening.views.Lab.objects.filter") as mock_lab:
            mock_lab.return_value.first.return_value = None
            response = PredictView.as_view()(request)

        assert response.status_code == status.HTTP_400_BAD_REQUEST  # lab not found, but past cache

    def test_recommendation_helper(self):
        """Test the _recommendation static method returns correct text."""
        assert "recommended" in PredictView._recommendation(3)
        assert "Consider" in PredictView._recommendation(2)
        assert "unlikely" in PredictView._recommendation(1)

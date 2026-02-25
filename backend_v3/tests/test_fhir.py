"""
Tests for the FHIR R4 Bundle endpoint.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.models import Role
from apps.screening.views import FHIRBundleView


def _make_user(role=Role.LAB, username="lab_user"):
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = False
    user.role = role
    user.pk = 1
    user.username = username
    user.token_payload = {"mfa_verified": True}
    return user


VALID_BUNDLE = {
    "resourceType": "Bundle",
    "type": "transaction",
    "entry": [
        {
            "resource": {
                "resourceType": "Patient",
                "id": "patient-001",
                "identifier": [{"value": "P001"}],
                "birthDate": "1980-06-15",
                "gender": "male",
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "code": {"coding": [{"system": "http://loinc.org", "code": "718-7"}]},
                "valueQuantity": {"value": 14.5},
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "code": {"coding": [{"system": "http://loinc.org", "code": "789-8"}]},
                "valueQuantity": {"value": 5.0},
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "code": {"coding": [{"system": "http://loinc.org", "code": "4544-3"}]},
                "valueQuantity": {"value": 43.5},
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "code": {"coding": [{"system": "http://loinc.org", "code": "787-2"}]},
                "valueQuantity": {"value": 87.0},
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "code": {"coding": [{"system": "http://loinc.org", "code": "785-6"}]},
                "valueQuantity": {"value": 29.5},
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "code": {"coding": [{"system": "http://loinc.org", "code": "786-4"}]},
                "valueQuantity": {"value": 33.5},
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "code": {"coding": [{"system": "http://loinc.org", "code": "788-0"}]},
                "valueQuantity": {"value": 13.2},
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "code": {"coding": [{"system": "http://loinc.org", "code": "6690-2"}]},
                "valueQuantity": {"value": 6.8},
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "code": {"coding": [{"system": "http://loinc.org", "code": "777-3"}]},
                "valueQuantity": {"value": 245.0},
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "code": {"coding": [{"system": "http://loinc.org", "code": "770-8"}]},
                "valueQuantity": {"value": 58.0},
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "code": {"coding": [{"system": "http://loinc.org", "code": "736-9"}]},
                "valueQuantity": {"value": 32.0},
            }
        },
    ],
}


def _post_bundle(bundle, user=None, lab_id="LAB-001"):
    factory = APIRequestFactory()
    url = "/api/screening/fhir/bundle"
    if lab_id:
        url += f"?labId={lab_id}"
    request = factory.post(url, bundle, format="json")
    user = user or _make_user()
    force_authenticate(request, user=user)
    request.token_payload = {"mfa_verified": True}
    return request


class TestFHIRBundleView:

    def test_wrong_resource_type_returns_400(self):
        bad_bundle = {"resourceType": "Patient", "id": "x"}
        request = _post_bundle(bad_bundle)
        response = FHIRBundleView.as_view()(request)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.screening.views.Lab.objects.filter")
    def test_missing_patient_resource_returns_400(self, mock_lab):
        mock_lab.return_value.first.return_value = MagicMock()
        bundle = {"resourceType": "Bundle", "type": "transaction", "entry": []}
        request = _post_bundle(bundle)
        response = FHIRBundleView.as_view()(request)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.screening.views.Lab.objects.filter")
    def test_missing_observations_returns_400(self, mock_lab):
        mock_lab.return_value.first.return_value = MagicMock()
        bundle = {
            "resourceType": "Bundle",
            "type": "transaction",
            "entry": [
                {"resource": {
                    "resourceType": "Patient",
                    "identifier": [{"value": "P001"}],
                    "birthDate": "1980-01-01",
                    "gender": "male",
                }}
            ],
        }
        request = _post_bundle(bundle)
        response = FHIRBundleView.as_view()(request)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Missing Observation" in str(response.data.get("error", ""))

    @patch("apps.screening.views.Lab.objects.filter")
    def test_invalid_birth_date_returns_400(self, mock_lab):
        mock_lab.return_value.first.return_value = MagicMock()
        bundle = {
            **VALID_BUNDLE,
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "identifier": [{"value": "P001"}],
                        "birthDate": "not-a-date",
                        "gender": "male",
                    }
                },
                *VALID_BUNDLE["entry"][1:],
            ],
        }
        request = _post_bundle(bundle)
        response = FHIRBundleView.as_view()(request)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.screening.views.log_phi_access")
    @patch("apps.screening.views.Screening.objects.create")
    @patch("apps.screening.views.Patient.objects.update_or_create")
    @patch("apps.screening.views.Lab.objects.filter")
    @patch("apps.screening.views.get_ml_engine")
    def test_valid_bundle_returns_201_diagnostic_report(
        self, mock_engine, mock_lab, mock_patient_uoc, mock_screening_create, mock_log
    ):
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

        lab = MagicMock()
        mock_lab.return_value.first.return_value = lab

        patient = MagicMock()
        mock_patient_uoc.return_value = (patient, True)

        screening = MagicMock()
        screening.id = uuid.uuid4()
        screening.created_at.isoformat.return_value = "2025-01-01T03:00:00+00:00"
        mock_screening_create.return_value = screening

        request = _post_bundle(VALID_BUNDLE)
        response = FHIRBundleView.as_view()(request)

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["resourceType"] == "DiagnosticReport"
        assert response.data["status"] == "final"
        assert response.data["conclusion"] == "Normal"

"""
Tests for doctor data isolation (Phase 0.2).

Verifies that a DOCTOR role user cannot access another doctor's patient data
by passing a doctorId query parameter to the CaseStatsView.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.analytics.views import CaseStatsView
from apps.core.models import Role


def make_user(role: str, email: str = "doctor@example.com") -> MagicMock:
    """Build a minimal mock user for the given role."""
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = False
    user.role = role
    user.email = email
    return user


def make_request(user, params: dict | None = None):
    """Construct a GET request to CaseStatsView."""
    factory = APIRequestFactory()
    request = factory.get("/api/analytics/cases/", params or {})
    force_authenticate(request, user=user)
    # Simulate JWTAuthentication setting the token payload
    request.token_payload = {"mfa_verified": True}
    return request


class TestDoctorIsolation:
    """Doctor role must only see their own patients."""

    @patch("apps.analytics.views.Doctor.objects.filter")
    @patch("apps.analytics.views.Screening.objects.select_related")
    def test_doctor_cannot_pass_doctorId_param(self, mock_screening, mock_doctor):
        """DOCTOR passing doctorId query param must receive 403."""
        user = make_user(Role.DOCTOR, email="doctor_a@example.com")
        request = make_request(user, params={"doctorId": "DOCTOR_B_CODE"})

        view = CaseStatsView.as_view()
        response = view(request)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "doctorId" in response.data.get("error", "").lower() or \
               "cannot" in response.data.get("error", "").lower(), \
            f"Expected informative 403 message, got: {response.data}"

    @patch("apps.analytics.views.Doctor.objects.filter")
    @patch("apps.analytics.views.Screening.objects.select_related")
    def test_doctor_sees_only_own_data_when_no_param(self, mock_select, mock_doctor_filter):
        """DOCTOR with no doctorId param is filtered to their own doctor record."""
        doctor_mock = MagicMock()
        doctor_mock.email = "doctor_a@example.com"
        mock_doctor_filter.return_value.first.return_value = doctor_mock

        # Fake screening queryset (empty, to focus on filtering logic)
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_qs.__getitem__ = MagicMock(return_value=[])
        mock_qs.__iter__ = MagicMock(return_value=iter([]))
        mock_select.return_value = mock_qs

        user = make_user(Role.DOCTOR, email="doctor_a@example.com")
        request = make_request(user)

        view = CaseStatsView.as_view()
        response = view(request)

        # Must succeed (200), not 403
        assert response.status_code == status.HTTP_200_OK
        # Doctor filter must have been called with the user's email
        mock_doctor_filter.assert_called_once_with(
            email="doctor_a@example.com", is_active=True
        )

    @patch("apps.analytics.views.Doctor.objects.filter")
    @patch("apps.analytics.views.Screening.objects.select_related")
    def test_doctor_with_no_matching_record_gets_empty_list(self, mock_select, mock_doctor_filter):
        """DOCTOR with no matching Doctor record gets an empty list, not an error."""
        mock_doctor_filter.return_value.first.return_value = None  # No doctor found

        user = make_user(Role.DOCTOR, email="unknown@example.com")
        request = make_request(user)

        view = CaseStatsView.as_view()
        response = view(request)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == []

    @patch("apps.analytics.views.Doctor.objects.filter")
    @patch("apps.analytics.views.Screening.objects.select_related")
    def test_lab_manager_can_filter_by_doctorId(self, mock_select, mock_doctor_filter):
        """LAB role may pass doctorId param freely."""
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_qs.__getitem__ = MagicMock(return_value=[])
        mock_qs.__iter__ = MagicMock(return_value=iter([]))
        mock_select.return_value = mock_qs

        user = make_user(Role.LAB, email="lab@example.com")
        request = make_request(user, params={"doctorId": "DOCTOR_B_CODE"})

        view = CaseStatsView.as_view()
        response = view(request)

        assert response.status_code == status.HTTP_200_OK
        # Filter by doctor__code should have been called
        mock_qs.filter.assert_any_call(doctor__code="DOCTOR_B_CODE")

    @patch("apps.analytics.views.Doctor.objects.filter")
    @patch("apps.analytics.views.Screening.objects.select_related")
    def test_lab_role_can_filter_by_doctorId(self, mock_select, mock_doctor_filter):
        """LAB role may pass doctorId param freely."""
        mock_qs = MagicMock()
        mock_qs.filter.return_value = mock_qs
        mock_qs.order_by.return_value = mock_qs
        mock_qs.__getitem__ = MagicMock(return_value=[])
        mock_qs.__iter__ = MagicMock(return_value=iter([]))
        mock_select.return_value = mock_qs

        user = make_user(Role.LAB, email="lab@example.com")
        request = make_request(user, params={"doctorId": "DOCTOR_B_CODE"})

        view = CaseStatsView.as_view()
        response = view(request)

        assert response.status_code == status.HTTP_200_OK

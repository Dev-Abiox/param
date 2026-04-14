"""
Tests for the doctor review workflow and the lab listing endpoint.

ReviewScreeningView (PATCH /api/screening/cases/<uuid>/review):
- Must enforce DOCTOR isolation: doctors can only review their own
  patients; cross-doctor reviews are 403.
- LAB role can review any screening.
- Missing screening → 404.
- Sets is_reviewed, reviewed_at, reviewed_by, and the optional note.

LabListView (GET /api/screening/labs):
- Response shape must match DRF page pagination: count / results / next.
- Default page size 50; max_page_size 200.
- Respects page_size query param up to the max.
- Only LAB / SUPER_ADMIN can read.

Both views are exercised as view-unit tests with APIRequestFactory so
we don't need a full tenant DB — we mock the ORM chains.
"""

from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.models import Role
from apps.screening.views import LabListView, ReviewScreeningView


def _make_user(role=Role.LAB, email='lab@example.com', username='lab_user'):
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = False
    user.role = role
    user.email = email
    user.username = username
    user.pk = 1
    return user


def _make_request(method, path, data=None, user=None, params=None):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    kwargs = {'format': 'json'} if data is not None else {}
    request = fn(path, data, **kwargs) if data is not None else fn(path, params or {})
    user = user or _make_user()
    force_authenticate(request, user=user)
    request.token_payload = {'mfa_verified': True}
    return request


# ── ReviewScreeningView ────────────────────────────────────────────────────────

class TestReviewScreeningView:

    @patch.object(ReviewScreeningView, 'throttle_classes', [])
    @patch('apps.screening.views.log_phi_access')
    @patch('apps.screening.views.Screening.objects.select_related')
    def test_lab_can_review_any_screening(self, mock_select, mock_log):
        screening = MagicMock()
        screening.id = 'SCR-001'
        screening.doctor_id = 99
        screening.patient = MagicMock(patient_id='P-001')
        screening.is_reviewed = False
        screening.reviewed_at = datetime.now(dt_timezone.utc)
        screening.reviewed_by = 'lab_user'
        screening.clinical_note = 'all good'
        mock_select.return_value.get.return_value = screening

        request = _make_request(
            'patch',
            '/api/screening/cases/SCR-001/review',
            {'clinical_note': 'all good'},
        )
        response = ReviewScreeningView.as_view()(request, screening_id='SCR-001')

        assert response.status_code == status.HTTP_200_OK
        assert response.data['is_reviewed'] is True
        screening.save.assert_called_once()
        mock_log.assert_called_once()

    @patch.object(ReviewScreeningView, 'throttle_classes', [])
    @patch('apps.screening.views.Screening.objects.select_related')
    def test_missing_screening_returns_404(self, mock_select):
        from apps.screening.models import Screening
        mock_select.return_value.get.side_effect = Screening.DoesNotExist

        request = _make_request(
            'patch', '/api/screening/cases/missing/review', {}
        )
        response = ReviewScreeningView.as_view()(request, screening_id='missing')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    @patch.object(ReviewScreeningView, 'throttle_classes', [])
    @patch('apps.screening.views.Doctor.objects.filter')
    @patch('apps.screening.views.Screening.objects.select_related')
    def test_doctor_cannot_review_other_doctors_screening(
        self, mock_select, mock_doctor_filter
    ):
        # Screening belongs to doctor_id=42, but the requesting doctor
        # record has id=99 — isolation must block with 403.
        screening = MagicMock()
        screening.id = 'SCR-002'
        screening.doctor_id = 42
        mock_select.return_value.get.return_value = screening

        my_doctor = MagicMock()
        my_doctor.id = 99
        mock_doctor_filter.return_value.first.return_value = my_doctor

        user = _make_user(role=Role.DOCTOR, email='doctor@example.com')
        request = _make_request(
            'patch', '/api/screening/cases/SCR-002/review', {}, user=user
        )
        response = ReviewScreeningView.as_view()(request, screening_id='SCR-002')

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @patch.object(ReviewScreeningView, 'throttle_classes', [])
    @patch('apps.screening.views.log_phi_access')
    @patch('apps.screening.views.Doctor.objects.filter')
    @patch('apps.screening.views.Screening.objects.select_related')
    def test_doctor_can_review_own_screening(
        self, mock_select, mock_doctor_filter, mock_log
    ):
        screening = MagicMock()
        screening.id = 'SCR-003'
        screening.doctor_id = 77
        screening.patient = MagicMock(patient_id='P-003')
        screening.is_reviewed = False
        screening.reviewed_at = datetime.now(dt_timezone.utc)
        screening.reviewed_by = 'doctor_user'
        screening.clinical_note = ''
        mock_select.return_value.get.return_value = screening

        my_doctor = MagicMock()
        my_doctor.id = 77
        mock_doctor_filter.return_value.first.return_value = my_doctor

        user = _make_user(role=Role.DOCTOR, email='doctor@example.com')
        request = _make_request(
            'patch', '/api/screening/cases/SCR-003/review', {}, user=user
        )
        response = ReviewScreeningView.as_view()(request, screening_id='SCR-003')

        assert response.status_code == status.HTTP_200_OK


# ── LabListView pagination ─────────────────────────────────────────────────────

def _fake_labs(count, start_id=1):
    labs = []
    for i in range(count):
        lab = MagicMock()
        lab.id = start_id + i
        lab.code = f'LAB-{start_id + i:03d}'
        lab.name = f'Lab {start_id + i}'
        lab.tier = 'BASIC'
        lab.doctors_count = 2
        lab.cases_count = 5
        labs.append(lab)
    return labs


class TestLabListView:

    @patch.object(LabListView, 'throttle_classes', [])
    @patch('apps.screening.views.Lab.objects.filter')
    def test_returns_paginated_envelope(self, mock_filter):
        labs = _fake_labs(25)
        qs = MagicMock()
        qs.count.return_value = 25
        qs.__getitem__.side_effect = lambda k: labs[k] if isinstance(k, slice) else labs[k]
        qs.__iter__.return_value = iter(labs)
        mock_filter.return_value.annotate.return_value.order_by.return_value = qs

        request = _make_request('get', '/api/screening/labs')
        response = LabListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        body = response.data
        # DRF PageNumberPagination envelope.
        assert 'count' in body
        assert 'results' in body
        assert body['count'] == 25
        assert len(body['results']) == 25  # fits on a single default page

    @patch.object(LabListView, 'throttle_classes', [])
    @patch('apps.screening.views.Lab.objects.filter')
    def test_page_size_query_param_caps_at_max(self, mock_filter):
        labs = _fake_labs(500)
        qs = MagicMock()
        qs.count.return_value = 500
        qs.__getitem__.side_effect = lambda k: labs[k] if isinstance(k, slice) else labs[k]
        qs.__iter__.return_value = iter(labs)
        mock_filter.return_value.annotate.return_value.order_by.return_value = qs

        # Asking for 10,000 should be clamped to max_page_size=200.
        request = _make_request(
            'get', '/api/screening/labs', params={'page_size': '10000'}
        )
        response = LabListView.as_view()(request)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 200

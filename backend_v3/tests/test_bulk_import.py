"""
Tests for the bulk import endpoint and Celery processing task.
"""

import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.models import Role
from apps.screening.models import BulkImportJob
from apps.screening.views import BulkImportStatusView, BulkImportView

VALID_CSV = (
    "patient_id,patient_name,lab_id,doctor_id,hb,rbc,hct,mcv,mch,mchc,rdw,wbc,plt,neu_pct,lym_pct,age,sex\n"
    "P001,Alice,LAB-001,D001,14.5,5.0,43.5,87.0,29.5,33.5,13.2,6.8,245,58,32,45,M\n"
    "P002,Bob,LAB-001,D001,9.8,3.2,30.1,108.0,36.5,33.8,18.5,3.5,145,45,45,62,M\n"
)

MISSING_COL_CSV = (
    "patient_id,patient_name,hb,rbc\n"
    "P001,Alice,14.5,5.0\n"
)


def _make_user(role=Role.LAB):
    user = MagicMock()
    user.is_authenticated = True
    user.is_superuser = False
    user.role = role
    user.pk = 1
    user.username = "lab_user"
    user.token_payload = {"mfa_verified": True}
    return user


def _csv_request(csv_text: str, user=None, lab_id="LAB-001"):
    factory = APIRequestFactory()
    csv_file = io.BytesIO(csv_text.encode())
    csv_file.name = "import.csv"
    csv_file.size = len(csv_text)
    url = "/api/screening/bulk-import"
    if lab_id:
        url += f"?labId={lab_id}"
    request = factory.post(
        url,
        {"file": csv_file},
        format="multipart",
    )
    user = user or _make_user()
    force_authenticate(request, user=user)
    request.token_payload = {"mfa_verified": True}
    return request


class TestBulkImportView:

    def test_missing_file_returns_400(self):
        factory = APIRequestFactory()
        request = factory.post("/api/screening/bulk-import", {}, format="multipart")
        user = _make_user()
        force_authenticate(request, user=user)
        request.token_payload = {"mfa_verified": True}
        response = BulkImportView.as_view()(request)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_columns_returns_400(self):
        request = _csv_request(MISSING_COL_CSV)
        response = BulkImportView.as_view()(request)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Missing CSV columns" in str(response.data.get("error", ""))

    @patch("apps.screening.tasks.process_bulk_import")
    @patch("apps.screening.views.BulkImportJob.objects.create")
    @patch("apps.screening.views.log_phi_access")
    @patch("apps.screening.models.Lab.objects.filter")
    def test_valid_csv_accepted_and_job_created(self, mock_lab_filter, mock_log, mock_create, mock_task):
        # Mock lab lookup
        mock_lab = MagicMock()
        mock_lab.code = "LAB-001"
        mock_lab_filter.return_value.first.return_value = mock_lab

        job = MagicMock()
        job.id = uuid.uuid4()
        job.status = BulkImportJob.JobStatus.PENDING
        job.total_rows = 0
        mock_create.return_value = job

        request = _csv_request(VALID_CSV)
        response = BulkImportView.as_view()(request)

        assert response.status_code == status.HTTP_202_ACCEPTED
        assert str(job.id) == response.data["jobId"]
        mock_task.delay.assert_called_once()

    def test_doctor_role_cannot_submit_bulk_import(self):
        user = _make_user(role=Role.DOCTOR)
        request = _csv_request(VALID_CSV, user=user)
        response = BulkImportView.as_view()(request)
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestBulkImportStatusView:

    @patch("apps.screening.views.BulkImportJob.objects.get")
    def test_status_returns_job_info(self, mock_get):
        job_id = uuid.uuid4()
        job = MagicMock()
        job.id = job_id
        job.status = BulkImportJob.JobStatus.PROCESSING
        job.total_rows = 100
        job.processed_rows = 42
        job.failed_rows = 2
        job.error_detail = []
        job.created_at.isoformat.return_value = "2025-01-01T03:00:00+00:00"
        job.updated_at.isoformat.return_value = "2025-01-01T03:01:00+00:00"
        mock_get.return_value = job

        factory = APIRequestFactory()
        request = factory.get(f"/api/screening/bulk-import/{job_id}/status")
        user = _make_user()
        force_authenticate(request, user=user)
        request.token_payload = {"mfa_verified": True}
        response = BulkImportStatusView.as_view()(request, job_id=job_id)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["processedRows"] == 42
        assert response.data["failedRows"] == 2

    @patch("apps.screening.views.BulkImportJob.objects.get")
    def test_unknown_job_returns_404(self, mock_get):
        mock_get.side_effect = BulkImportJob.DoesNotExist

        job_id = uuid.uuid4()
        factory = APIRequestFactory()
        request = factory.get(f"/api/screening/bulk-import/{job_id}/status")
        user = _make_user()
        force_authenticate(request, user=user)
        request.token_payload = {"mfa_verified": True}
        response = BulkImportStatusView.as_view()(request, job_id=job_id)
        assert response.status_code == status.HTTP_404_NOT_FOUND

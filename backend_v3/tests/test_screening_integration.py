"""
Integration tests for screening endpoints.

Tests real database interactions for predict, work queue, and review flows.
Validates PHI is not leaked and doctor isolation is enforced.
"""

import pytest
from django_tenants.utils import tenant_context
from rest_framework.test import APIClient

from apps.screening.models import Lab, Doctor, ScreeningStatus


@pytest.mark.django_db
class TestWorkQueueIntegration:
    """Test GET /api/screening/queue."""

    def test_work_queue_returns_counts_and_items(self, authenticated_lab_user, test_tenant):
        user, token = authenticated_lab_user
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        # Set tenant context via X-Org-Id or let middleware handle it
        response = client.get('/api/screening/queue?status=pending')
        # May return 200 with empty list or items
        assert response.status_code == 200
        data = response.json()
        assert 'counts' in data
        assert 'items' in data
        assert 'pagination' in data

    def test_work_queue_does_not_leak_phi(self, authenticated_lab_user, test_tenant):
        """Verify patient initials are NOT included in work queue response."""
        user, token = authenticated_lab_user

        # Create a screening in the tenant
        with tenant_context(test_tenant):
            from tests.factories import ScreeningFactory
            ScreeningFactory(status=ScreeningStatus.PENDING)

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = client.get('/api/screening/queue?status=pending')

        if response.status_code == 200:
            data = response.json()
            for item in data.get('items', []):
                # patientInitials should NOT be present (PHI leak fix)
                assert 'patientInitials' not in item, \
                    "PHI leak: patientInitials should not appear in work queue response"
                # patientId (non-PHI identifier) is acceptable
                assert 'patientId' in item

    def test_work_queue_invalid_status_returns_400(self, authenticated_lab_user):
        user, token = authenticated_lab_user
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = client.get('/api/screening/queue?status=invalid')
        assert response.status_code == 400

    def test_doctor_cannot_access_work_queue(self, authenticated_doctor_user):
        user, token = authenticated_doctor_user
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = client.get('/api/screening/queue?status=pending')
        assert response.status_code == 403


@pytest.mark.django_db
class TestCaseListIntegration:
    """Test GET /api/screening/cases."""

    def test_lab_can_list_cases(self, authenticated_lab_user):
        user, token = authenticated_lab_user
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = client.get('/api/screening/cases')
        assert response.status_code == 200

    def test_unauthenticated_cannot_list_cases(self, public_tenant):
        client = APIClient()
        response = client.get('/api/screening/cases')
        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestLabIsolation:
    """Verify LAB-role users cannot reach records owned by a different lab.

    Backstop for the lab-scope guards added across screening / analytics
    endpoints. Uses a real DB so the autouse `_validate_lab_association`
    stub (which short-circuits to (None, None) for mock-only tests) does
    NOT apply — the actual production guard runs here.
    """

    def test_lab_user_cannot_view_patient_trend_in_other_lab(self, test_tenant, db):
        from apps.core.models import Role, User
        from apps.core.authentication import create_access_token
        from apps.screening.models import Patient
        from apps.core.crypto import encrypt_field

        with tenant_context(test_tenant):
            lab_a = Lab.objects.create(code='ISO-LAB-A', name='Lab A', is_active=True)
            lab_b = Lab.objects.create(code='ISO-LAB-B', name='Lab B', is_active=True)

            # _validate_lab_association picks the first active lab — make sure
            # that's lab_a deterministically by ordering. Both labs were just
            # created in this transaction so ordering by created_at puts the
            # first-inserted row first.
            assert Lab.objects.filter(is_active=True).order_by('created_at').first().code == 'ISO-LAB-A'

            # One patient in each lab — the lab_b patient is what we expect to be hidden.
            Patient.objects.create(
                patient_id='LAB-A-PATIENT', lab=lab_a,
                name_encrypted=encrypt_field('Alice'),
            )
            Patient.objects.create(
                patient_id='LAB-B-PATIENT', lab=lab_b,
                name_encrypted=encrypt_field('Bob'),
            )

            # LAB user — _validate_lab_association will resolve to lab_a (first active).
            lab_user = User.objects.create_user(
                username='iso_lab_user', email='iso_lab_user@clinomic.test',
                password='TestPass123!@#', role=Role.LAB,
                organization=test_tenant,
            )

        token = create_access_token(lab_user, mfa_verified=True)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

        # Reaching their own lab's patient must work.
        own_resp = client.get('/api/analytics/trend/LAB-A-PATIENT')
        assert own_resp.status_code == 200, \
            f'LAB-A user denied access to LAB-A patient: {own_resp.status_code} {own_resp.content!r}'

        # Reaching the OTHER lab's patient must return 404 — the patient row
        # exists in this tenant but is scoped out by the lab guard.
        leak_resp = client.get('/api/analytics/trend/LAB-B-PATIENT')
        assert leak_resp.status_code == 404, \
            f'Cross-lab leak: LAB-A user reached LAB-B patient (got {leak_resp.status_code})'


@pytest.mark.django_db
class TestDoctorIsolation:
    """Verify DOCTOR role data isolation is enforced."""

    def test_doctor_cannot_review_other_doctors_screening(self, test_tenant, db):
        from apps.core.models import Role, User
        from apps.core.authentication import create_access_token

        with tenant_context(test_tenant):
            # Create two doctors and their screenings
            lab = Lab.objects.create(code='ISO-LAB', name='Isolation Lab', is_active=True)
            doc_a = Doctor.objects.create(
                code='DA001', name='Dr. A', lab=lab,
                email='dra@clinomic.test', is_active=True,
            )
            doc_b = Doctor.objects.create(
                code='DB001', name='Dr. B', lab=lab,
                email='drb@clinomic.test', is_active=True,
            )

            # Create user for doctor A
            user_a = User.objects.create_user(
                username='dra_user', email='dra@clinomic.test',
                password='TestPass123!@#', role=Role.DOCTOR,
                organization=test_tenant,
            )

            # Create screening assigned to doctor B
            from tests.factories import ScreeningFactory
            screening_b = ScreeningFactory(doctor=doc_b, lab=lab)

        token_a = create_access_token(user_a, mfa_verified=True)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_a}')

        # Doctor A tries to review Doctor B's screening
        response = client.patch(
            f'/api/screening/cases/{screening_b.id}/review',
            {'clinical_note': 'Reviewed'},
            format='json',
        )
        assert response.status_code == 403

"""
Pytest configuration and fixtures for Clinomic v3 tests.

Uses django_tenants.postgresql_backend for tenant-aware testing.
"""

import os
import uuid

import pytest
from django.conf import settings
from django.test import override_settings

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinomic.settings')

# Set default environment variables for tests
os.environ.setdefault('DJANGO_SECRET_KEY', 'test-secret-key-for-testing-only-not-production')
os.environ.setdefault('MASTER_ENCRYPTION_KEY', 'vXR9o6LX2YVy0aIYIvlq5tFyRp-kXHjnNzOm8o-mkYQ=')
os.environ.setdefault('AUDIT_SIGNING_KEY', 'test-audit-key-for-testing-only-not-production')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret-key-for-testing-only-not-prod')
os.environ.setdefault('POSTGRES_DB', 'clinomic_test')
os.environ.setdefault('POSTGRES_USER', 'postgres')
os.environ.setdefault('POSTGRES_PASSWORD', 'postgres')
os.environ.setdefault('POSTGRES_HOST', 'localhost')
os.environ.setdefault('POSTGRES_PORT', '5432')
os.environ.setdefault('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('DEBUG', 'True')
os.environ.setdefault('APP_ENV', 'testing')

# Ensure Django is configured
import django
django.setup()

# Generate test encryption key
TEST_ENCRYPTION_KEY = "vXR9o6LX2YVy0aIYIvlq5tFyRp-kXHjnNzOm8o-mkYQ="


# NOTE: django_db_setup is NOT overridden here.
# settings.py already configures ENGINE='django_tenants.postgresql_backend'
# and DATABASE_ROUTERS. Letting pytest-django's default django_db_setup
# handle test DB creation ensures migrate_schemas runs correctly.


@pytest.fixture
def encryption_key():
    """Provide test encryption key."""
    return TEST_ENCRYPTION_KEY


@pytest.fixture
def test_org_id():
    """Provide consistent test organization ID."""
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def test_user_id():
    """Provide consistent test user ID."""
    return uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
def sample_cbc_data():
    """Provide sample CBC data for screening tests."""
    return {
        "Haemoglobin": 14.5,
        "MCV": 88.0,
        "MCH": 29.5,
        "MCHC": 33.5,
        "RDW_CV": 13.2,
        "WBC": 6.8,
        "Platelet": 245,
        "Neutrophils": 58.0,
        "Lymphocytes": 32.0,
        "Monocytes": 6.0,
        "Eosinophils": 3.0,
        "Basophils": 1.0,
        "LUC": 0.0,
    }


@pytest.fixture
def sample_cbc_deficient():
    """Provide sample CBC data indicating B12 deficiency."""
    return {
        "Haemoglobin": 9.8,
        "MCV": 108.0,
        "MCH": 36.5,
        "MCHC": 33.8,
        "RDW_CV": 18.5,
        "WBC": 3.5,
        "Platelet": 145,
        "Neutrophils": 45.0,
        "Lymphocytes": 45.0,
        "Monocytes": 6.0,
        "Eosinophils": 3.0,
        "Basophils": 1.0,
        "LUC": 0.0,
    }


# ---------------------------------------------------------------------------
# Tenant-aware fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
@pytest.mark.django_db
def public_tenant(db):
    """Create or retrieve the public schema tenant."""
    from django.db import connection
    from apps.core.models import Organization, Domain
    # Ensure we're in the public schema (previous tests may leave a tenant schema active)
    connection.set_schema_to_public()
    tenant, _ = Organization.objects.get_or_create(
        schema_name='public',
        defaults={'name': 'Public', 'is_active': True},
    )
    Domain.objects.get_or_create(
        domain='localhost',
        tenant=tenant,
        defaults={'is_primary': True},
    )
    # Django's test client uses 'testserver' as the default Host header
    Domain.objects.get_or_create(
        domain='testserver',
        tenant=tenant,
        defaults={'is_primary': False},
    )
    return tenant


@pytest.fixture
@pytest.mark.django_db
def test_tenant(db, public_tenant):
    """Create a test tenant with its own schema."""
    from apps.core.models import Organization, Domain
    tenant = Organization.objects.create(
        name='Test Org',
        schema_name='test_org',
        is_active=True,
    )
    Domain.objects.create(
        domain='test-org.localhost',
        tenant=tenant,
        is_primary=True,
    )
    return tenant


@pytest.fixture
@pytest.mark.django_db
def authenticated_lab_user(test_tenant, db):
    """Create a LAB user with a valid access token for the test tenant."""
    from django_tenants.utils import tenant_context
    from apps.core.models import Role, User
    from apps.core.authentication import create_access_token

    with tenant_context(test_tenant):
        user = User.objects.create_user(
            username='testlab',
            email='testlab@clinomic.test',
            password='TestPass123!@#',
            role=Role.LAB,
            organization=test_tenant,
        )
    token = create_access_token(user, mfa_verified=True)
    return user, token


@pytest.fixture
@pytest.mark.django_db
def authenticated_doctor_user(test_tenant, db):
    """Create a DOCTOR user with a valid access token for the test tenant."""
    from django_tenants.utils import tenant_context
    from apps.core.models import Role, User
    from apps.core.authentication import create_access_token

    with tenant_context(test_tenant):
        user = User.objects.create_user(
            username='testdoctor',
            email='testdoctor@clinomic.test',
            password='TestPass123!@#',
            role=Role.DOCTOR,
            organization=test_tenant,
        )
    token = create_access_token(user, mfa_verified=True)
    return user, token


@pytest.fixture
@pytest.mark.django_db
def authenticated_superadmin(db, public_tenant):
    """Create a SUPER_ADMIN user (no tenant) with a valid access token."""
    from apps.core.models import Role, User
    from apps.core.authentication import create_access_token

    user = User.objects.create_user(
        username='testsuperadmin',
        email='testsuperadmin@clinomic.test',
        password='TestPass123!@#',
        role=Role.SUPER_ADMIN,
        is_superuser=True,
        is_staff=True,
        organization=None,
    )
    token = create_access_token(user, mfa_verified=True)
    return user, token

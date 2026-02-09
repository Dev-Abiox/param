"""
Pytest configuration and fixtures for Clinomic v3 tests.
"""

import os
import uuid

import pytest
from django.conf import settings
from django.test import override_settings

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clinomic.settings')

# Set default environment variables for tests
os.environ.setdefault('DJANGO_SECRET_KEY', 'test-secret-key-for-testing')
os.environ.setdefault('MASTER_ENCRYPTION_KEY', 'dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==')  # Base64 encoded test key
os.environ.setdefault('AUDIT_SIGNING_KEY', 'test-audit-key')
os.environ.setdefault('JWT_SECRET_KEY', 'test-jwt-secret')
os.environ.setdefault('POSTGRES_DB', 'clinomic_test')
os.environ.setdefault('POSTGRES_USER', 'postgres')
os.environ.setdefault('POSTGRES_PASSWORD', 'postgres')
os.environ.setdefault('POSTGRES_HOST', 'localhost')
os.environ.setdefault('POSTGRES_PORT', '5432')
os.environ.setdefault('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')
os.environ.setdefault('DEBUG', 'True')

# Ensure Django is configured
import django
django.setup()

# Generate test encryption key
TEST_ENCRYPTION_KEY = "dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw=="  # Base64 encoded


@pytest.fixture(scope="session")
def django_db_setup():
    """Configure test database."""
    settings.DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "clinomic_test",
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "postgres"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }


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

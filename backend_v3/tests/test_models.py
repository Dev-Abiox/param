"""
Tests for Django models (core and screening).
"""

import uuid

import pytest
from django.test import TestCase, override_settings


class TestUserModel:
    """Tests for the User model."""

    def test_user_model_import(self):
        """Test User model can be imported."""
        from apps.core.models import User

        assert User is not None

    def test_user_role_choices(self):
        """Test User role choices are defined."""
        from apps.core.models import Role

        assert Role.ADMIN == "ADMIN"
        assert Role.LAB == "LAB"
        assert Role.DOCTOR == "DOCTOR"

    def test_user_str_representation(self):
        """Test User string representation."""
        from apps.core.models import User

        user = User(username="testuser", role="LAB")
        assert "testuser" in str(user)
        assert "LAB" in str(user)


class TestOrganizationModel:
    """Tests for the Organization model."""

    def test_organization_model_import(self):
        """Test Organization model can be imported."""
        from apps.core.models import Organization

        assert Organization is not None

    def test_organization_tier_choices(self):
        """Test Organization tier choices."""
        from apps.core.models import Organization

        org = Organization(name="Test Lab", tier="pilot")
        assert org.tier == "pilot"

    def test_organization_str_representation(self):
        """Test Organization string representation."""
        from apps.core.models import Organization

        org = Organization(name="Test Lab")
        assert str(org) == "Test Lab"


class TestAuditLogEntry:
    """Tests for the AuditLogEntry model."""

    def test_audit_log_model_import(self):
        """Test AuditLogEntry model can be imported."""
        from apps.core.models import AuditLogEntry

        assert AuditLogEntry is not None

    def test_audit_log_has_hash_fields(self):
        """Test AuditLogEntry has hash chain fields."""
        from apps.core.models import AuditLogEntry

        # Check model has required hash chain fields
        field_names = [f.name for f in AuditLogEntry._meta.get_fields()]

        assert "previous_hash" in field_names
        assert "entry_hash" in field_names
        assert "signature" in field_names


class TestLabModel:
    """Tests for the Lab model."""

    def test_lab_model_import(self):
        """Test Lab model can be imported."""
        from apps.screening.models import Lab

        assert Lab is not None

    def test_lab_str_representation(self):
        """Test Lab string representation."""
        from apps.screening.models import Lab

        lab = Lab(code="LAB-001", name="Test Laboratory")
        assert "LAB-001" in str(lab)
        assert "Test Laboratory" in str(lab)


class TestDoctorModel:
    """Tests for the Doctor model."""

    def test_doctor_model_import(self):
        """Test Doctor model can be imported."""
        from apps.screening.models import Doctor

        assert Doctor is not None


class TestPatientModel:
    """Tests for the Patient model."""

    def test_patient_model_import(self):
        """Test Patient model can be imported."""
        from apps.screening.models import Patient

        assert Patient is not None

    def test_patient_has_encrypted_name_field(self):
        """Test Patient has encrypted name field."""
        from apps.screening.models import Patient

        field_names = [f.name for f in Patient._meta.get_fields()]
        assert "name_encrypted" in field_names

    @override_settings(MASTER_ENCRYPTION_KEY="dGVzdC1lbmNyeXB0aW9uLWtleS0zMi1ieXRlcw==")
    def test_patient_name_property_encrypts(self):
        """Test Patient name property encrypts data."""
        from apps.core import crypto
        crypto._cipher = None  # Reset cipher

        from apps.screening.models import Patient

        patient = Patient()
        patient.name = "John Doe"

        # Should be encrypted
        assert patient.name_encrypted != "John Doe"
        assert len(patient.name_encrypted) > 0


class TestScreeningModel:
    """Tests for the Screening model."""

    def test_screening_model_import(self):
        """Test Screening model can be imported."""
        from apps.screening.models import Screening

        assert Screening is not None

    def test_risk_class_choices(self):
        """Test RiskClass choices are defined."""
        from apps.screening.models import RiskClass

        assert RiskClass.NORMAL == 1
        assert RiskClass.BORDERLINE == 2
        assert RiskClass.DEFICIENT == 3

    def test_screening_has_required_fields(self):
        """Test Screening has all required fields."""
        from apps.screening.models import Screening

        field_names = [f.name for f in Screening._meta.get_fields()]

        required = [
            "patient",
            "lab",
            "risk_class",
            "probabilities",
            "cbc_snapshot",
            "model_version",
            "request_hash",
            "response_hash",
        ]

        for field in required:
            assert field in field_names, f"Missing field: {field}"


class TestConsentModel:
    """Tests for the Consent model."""

    def test_consent_model_import(self):
        """Test Consent model can be imported."""
        from apps.screening.models import Consent

        assert Consent is not None

    def test_consent_status_choices(self):
        """Test Consent status choices."""
        from apps.screening.models import Consent

        # Test model accepts valid status values
        consent = Consent()
        consent.status = "active"
        assert consent.status == "active"

        consent.status = "revoked"
        assert consent.status == "revoked"

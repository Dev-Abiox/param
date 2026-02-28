"""
factory_boy factories for all core models.

Usage in tests:
    from tests.factories import UserFactory, LabFactory, DoctorFactory, PatientFactory, ScreeningFactory

All factories use the 'django' strategy by default; wrap test methods with
@pytest.mark.django_db or use the db fixture from pytest-django.
"""

import uuid

import factory
from factory.django import DjangoModelFactory

from apps.core.models import Domain, Organization, Role, User
from apps.core.crypto import encrypt_field
from apps.screening.models import BulkImportJob, Consent, Doctor, Lab, Patient, Screening, ScreeningStatus


class OrganizationFactory(DjangoModelFactory):
    class Meta:
        model = Organization

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"Test Org {n}")
    schema_name = factory.Sequence(lambda n: f"test_org_{n}")
    is_active = True


class DomainFactory(DjangoModelFactory):
    class Meta:
        model = Domain

    domain = factory.LazyAttribute(lambda o: f"{o.tenant.schema_name}.localhost")
    tenant = factory.SubFactory(OrganizationFactory)
    is_primary = True


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User

    id       = factory.LazyFunction(uuid.uuid4)
    username = factory.Sequence(lambda n: f"user{n}")
    email    = factory.LazyAttribute(lambda o: f"{o.username}@clinomic.test")
    role     = Role.LAB
    is_active = True
    organization = factory.SubFactory(OrganizationFactory)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop('password', 'TestPass123!')
        obj = model_class(**kwargs)
        obj.set_password(password)
        obj.save()
        return obj


class LabManagerFactory(UserFactory):
    role = Role.LAB
    username = factory.Sequence(lambda n: f"labmgr{n}")


class DoctorUserFactory(UserFactory):
    role = Role.DOCTOR
    username = factory.Sequence(lambda n: f"doctor_user{n}")


class LabFactory(DjangoModelFactory):
    class Meta:
        model = Lab

    id         = factory.LazyFunction(uuid.uuid4)
    code       = factory.Sequence(lambda n: f"LAB-{n:04d}")
    name       = factory.Sequence(lambda n: f"Test Lab {n}")
    tier       = 'standard'
    is_active  = True


class DoctorFactory(DjangoModelFactory):
    class Meta:
        model = Doctor

    id     = factory.LazyFunction(uuid.uuid4)
    code   = factory.Sequence(lambda n: f"D{n:04d}")
    name   = factory.Sequence(lambda n: f"Dr. Test {n}")
    lab    = factory.SubFactory(LabFactory)
    email  = factory.Sequence(lambda n: f"doctor{n}@clinomic.test")
    is_active = True


class PatientFactory(DjangoModelFactory):
    class Meta:
        model = Patient

    id         = factory.LazyFunction(uuid.uuid4)
    patient_id = factory.Sequence(lambda n: f"P{n:06d}")
    lab        = factory.SubFactory(LabFactory)

    # Encrypted PHI
    name_encrypted = factory.LazyFunction(lambda: encrypt_field("Test Patient"))
    age_encrypted  = factory.LazyFunction(lambda: encrypt_field("45"))
    sex_encrypted  = factory.LazyFunction(lambda: encrypt_field("M"))


class ScreeningFactory(DjangoModelFactory):
    class Meta:
        model = Screening

    id      = factory.LazyFunction(uuid.uuid4)
    patient = factory.SubFactory(PatientFactory)
    lab     = factory.LazyAttribute(lambda o: o.patient.lab)
    doctor  = None
    performed_by = "lab_user"

    risk_class   = 1
    label_text   = "Normal"
    probabilities = factory.LazyFunction(lambda: {'normal': 0.85, 'borderline': 0.10, 'deficient': 0.05})
    rules_fired  = factory.LazyFunction(list)
    cbc_snapshot = factory.LazyFunction(lambda: {
        'Hb_g_dL': 14.5, 'RBC_million_uL': 5.0, 'HCT_percent': 43.5,
        'MCV_fL': 87.0, 'MCH_pg': 29.5, 'MCHC_g_dL': 33.5, 'RDW_percent': 13.2,
        'WBC_10_3_uL': 6.8, 'Platelets_10_3_uL': 245.0,
        'Neutrophils_percent': 58.0, 'Lymphocytes_percent': 32.0,
        'Age': 45, 'Sex': 'M',
    })
    indices            = factory.LazyFunction(dict)
    model_version      = 'v1.0.0'
    model_artifact_hash = factory.LazyFunction(lambda: 'a' * 64)
    request_hash       = factory.LazyFunction(lambda: 'b' * 64)
    response_hash      = factory.LazyFunction(lambda: 'c' * 64)
    screening_hash     = factory.LazyFunction(lambda: 'd' * 64)
    status             = ScreeningStatus.PENDING


class DeficientScreeningFactory(ScreeningFactory):
    risk_class  = 3
    label_text  = "Deficient"
    probabilities = factory.LazyFunction(lambda: {'normal': 0.05, 'borderline': 0.10, 'deficient': 0.85})


class ConsentFactory(DjangoModelFactory):
    class Meta:
        model = Consent

    id             = factory.LazyFunction(uuid.uuid4)
    patient        = factory.SubFactory(PatientFactory)
    consent_type   = 'screening'
    consent_text   = 'I consent to B12 deficiency screening.'
    consented_by   = 'lab_user'
    consent_method = 'verbal'
    status         = 'active'
    consented_at   = factory.LazyFunction(lambda: __import__('datetime').datetime.now(__import__('datetime').timezone.utc))


class BulkImportJobFactory(DjangoModelFactory):
    class Meta:
        model = BulkImportJob

    id           = factory.LazyFunction(uuid.uuid4)
    submitted_by = 'lab_user'
    status       = BulkImportJob.JobStatus.PENDING
    total_rows   = 0

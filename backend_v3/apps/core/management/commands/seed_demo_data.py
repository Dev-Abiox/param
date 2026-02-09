"""
Management command for seeding demo data in the Clinomic B12 Screening Platform.

Uses deterministic UUIDs to ensure idempotent seeding (no duplicate data).
Run with: python manage.py seed_demo_data
"""

import hashlib
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection, transaction
from django.utils import timezone
from django_tenants.utils import schema_context

from apps.core.crypto import encrypt_field, is_crypto_ready
from apps.core.models import Domain, Organization, Role, User
from apps.screening.models import Consent, Doctor, Lab, Patient, RiskClass, Screening


def deterministic_uuid(namespace: str, name: str) -> uuid.UUID:
    """Generate a deterministic UUID from namespace and name for idempotent seeding."""
    combined = f"{namespace}:{name}"
    hash_bytes = hashlib.sha256(combined.encode()).digest()[:16]
    return uuid.UUID(bytes=hash_bytes)


DEMO_NAMESPACE = "clinomic-demo-v3"


class Command(BaseCommand):
    help = "Seed demo data for the Clinomic B12 Screening Platform (idempotent)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clean",
            action="store_true",
            help="Remove all demo data before seeding",
        )
        parser.add_argument(
            "--skip-screenings",
            action="store_true",
            help="Skip creating demo screenings (faster seeding)",
        )

    def handle(self, *args, **options):
        if not is_crypto_ready():
            self.stderr.write(
                self.style.ERROR(
                    "MASTER_ENCRYPTION_KEY not configured. "
                    "Set it in your environment before seeding."
                )
            )
            return

        if options["clean"]:
            self.clean_demo_data()

        self.stdout.write("Seeding demo data...")

        # Create shared schema data (organization, domain)
        org = self.create_organization()

        # Create tenant-specific data
        with schema_context(org.schema_name):
            users = self.create_users(org)
            lab = self.create_lab()
            doctors = self.create_doctors(lab)
            patients = self.create_patients(lab, doctors)

            if not options["skip_screenings"]:
                self.create_screenings(patients, lab, doctors, users)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDemo data seeded successfully!\n"
                f"  Organization: {org.name} (schema: {org.schema_name})\n"
                f"  Domains: demo.localhost, localhost\n"
                f"  Users: admin_demo (admin), lab_demo (lab), doctor_demo (doctor)\n"
                f"  Password: Demo@2024\n"
            )
        )

    def clean_demo_data(self):
        """Remove all demo data."""
        self.stdout.write("Cleaning existing demo data...")

        # Get demo org
        org_id = deterministic_uuid(DEMO_NAMESPACE, "organization:demo")
        try:
            org = Organization.objects.get(id=org_id)

            # Delete tenant schema
            with schema_context(org.schema_name):
                Screening.objects.all().delete()
                Consent.objects.all().delete()
                Patient.objects.all().delete()
                Doctor.objects.all().delete()
                Lab.objects.all().delete()

            # Delete users and organization
            User.objects.filter(organization=org).delete()
            Domain.objects.filter(tenant=org).delete()
            org.delete()

            self.stdout.write(self.style.SUCCESS("Demo data cleaned."))
        except Organization.DoesNotExist:
            self.stdout.write("No existing demo data found.")

    @transaction.atomic
    def create_organization(self):
        """Create demo organization with domain."""
        org_id = deterministic_uuid(DEMO_NAMESPACE, "organization:demo")

        org, created = Organization.objects.update_or_create(
            id=org_id,
            defaults={
                "name": "Demo Lab",
                "tier": "pilot",
                "schema_name": "demo_lab",
                "is_active": True,
            },
        )

        if created:
            self.stdout.write(f"  Created organization: {org.name}")
        else:
            self.stdout.write(f"  Organization exists: {org.name}")

        # Create domain (uses auto-increment ID, not UUID)
        domain, created = Domain.objects.get_or_create(
            domain="demo.localhost",
            defaults={
                "tenant": org,
                "is_primary": True,
            },
        )

        if created:
            self.stdout.write(f"  Created domain: {domain.domain}")
        else:
            self.stdout.write(f"  Domain exists: {domain.domain}")

        # Also add localhost for local development
        localhost_domain, created = Domain.objects.get_or_create(
            domain="localhost",
            defaults={
                "tenant": org,
                "is_primary": False,
            },
        )

        if created:
            self.stdout.write(f"  Created domain: {localhost_domain.domain}")

        return org

    def create_users(self, org):
        """Create demo users with different roles."""
        users = {}
        default_password = "Demo@2024"

        user_configs = [
            {
                "key": "admin_demo",
                "username": "admin_demo",
                "role": Role.ADMIN,
                "name": "Demo Administrator",
                "email": "admin@demo.clinomic.local",
                "is_staff": True,
            },
            {
                "key": "lab_demo",
                "username": "lab_demo",
                "role": Role.LAB,
                "name": "Demo Lab Technician",
                "email": "lab@demo.clinomic.local",
                "is_staff": False,
            },
            {
                "key": "doctor_demo",
                "username": "doctor_demo",
                "role": Role.DOCTOR,
                "name": "Dr. Demo Physician",
                "email": "doctor@demo.clinomic.local",
                "is_staff": False,
            },
        ]

        for config in user_configs:
            user_id = deterministic_uuid(DEMO_NAMESPACE, f"user:{config['key']}")

            user, created = User.objects.update_or_create(
                id=user_id,
                defaults={
                    "username": config["username"],
                    "role": config["role"],
                    "name": config["name"],
                    "email": config["email"],
                    "is_staff": config["is_staff"],
                    "organization": org,
                    "is_active": True,
                },
            )

            if created:
                user.set_password(default_password)
                user.save()
                self.stdout.write(f"  Created user: {user.username} ({user.role})")
            else:
                self.stdout.write(f"  User exists: {user.username}")

            users[config["key"]] = user

        return users

    def create_lab(self):
        """Create demo lab."""
        lab_id = deterministic_uuid(DEMO_NAMESPACE, "lab:demo")

        lab, created = Lab.objects.update_or_create(
            id=lab_id,
            defaults={
                "code": "LAB-DEMO-001",
                "name": "Demo Diagnostic Laboratory",
                "tier": "pilot",
                "address": "123 Demo Street, Demo City, DC 12345",
                "contact_email": "lab@demo.clinomic.local",
                "is_active": True,
            },
        )

        if created:
            self.stdout.write(f"  Created lab: {lab.name}")
        else:
            self.stdout.write(f"  Lab exists: {lab.name}")

        return lab

    def create_doctors(self, lab):
        """Create demo doctors."""
        doctors = {}

        doctor_configs = [
            {
                "key": "d101",
                "code": "D101",
                "name": "Dr. Sarah Johnson",
                "department": "Internal Medicine",
                "specialization": "Hematology",
            },
            {
                "key": "d102",
                "code": "D102",
                "name": "Dr. Michael Chen",
                "department": "General Practice",
                "specialization": "Family Medicine",
            },
            {
                "key": "d103",
                "code": "D103",
                "name": "Dr. Emily Rodriguez",
                "department": "Neurology",
                "specialization": "Neurological Disorders",
            },
        ]

        for config in doctor_configs:
            doctor_id = deterministic_uuid(DEMO_NAMESPACE, f"doctor:{config['key']}")

            doctor, created = Doctor.objects.update_or_create(
                id=doctor_id,
                defaults={
                    "code": config["code"],
                    "name": config["name"],
                    "department": config["department"],
                    "specialization": config["specialization"],
                    "lab": lab,
                    "email": f"{config['key'].lower()}@demo.clinomic.local",
                    "is_active": True,
                },
            )

            if created:
                self.stdout.write(f"  Created doctor: {doctor.name}")

            doctors[config["key"]] = doctor

        return doctors

    def create_patients(self, lab, doctors):
        """Create demo patients with encrypted names."""
        patients = {}

        patient_configs = [
            # Normal range patients
            {"key": "p001", "pid": "P-2024-001", "name": "John Smith", "age": 45, "sex": "M", "doctor": "d101"},
            {"key": "p002", "pid": "P-2024-002", "name": "Mary Johnson", "age": 62, "sex": "F", "doctor": "d101"},
            # Borderline patients
            {"key": "p003", "pid": "P-2024-003", "name": "Robert Davis", "age": 38, "sex": "M", "doctor": "d102"},
            {"key": "p004", "pid": "P-2024-004", "name": "Lisa Anderson", "age": 55, "sex": "F", "doctor": "d102"},
            # Deficient patients
            {"key": "p005", "pid": "P-2024-005", "name": "James Wilson", "age": 72, "sex": "M", "doctor": "d103"},
            {"key": "p006", "pid": "P-2024-006", "name": "Patricia Brown", "age": 28, "sex": "F", "doctor": "d103"},
            # Additional patients
            {"key": "p007", "pid": "P-2024-007", "name": "William Taylor", "age": 50, "sex": "M", "doctor": "d101"},
            {"key": "p008", "pid": "P-2024-008", "name": "Jennifer Martinez", "age": 41, "sex": "F", "doctor": "d102"},
        ]

        for config in patient_configs:
            patient_id = deterministic_uuid(DEMO_NAMESPACE, f"patient:{config['key']}")

            patient, created = Patient.objects.update_or_create(
                id=patient_id,
                defaults={
                    "patient_id": config["pid"],
                    "name_encrypted": encrypt_field(config["name"]),
                    "age": config["age"],
                    "sex": config["sex"],
                    "lab": lab,
                    "referring_doctor": doctors.get(config["doctor"]),
                },
            )

            if created:
                self.stdout.write(f"  Created patient: {config['pid']}")

            patients[config["key"]] = patient

        return patients

    def create_screenings(self, patients, lab, doctors, users):
        """Create demo screenings with realistic CBC values."""
        self.stdout.write("  Creating demo screenings...")

        # Sample CBC data for different risk classifications
        screening_configs = [
            # Normal (Class 1)
            {
                "patient": "p001",
                "doctor": "d101",
                "risk_class": RiskClass.NORMAL,
                "label": "Normal",
                "probs": {"normal": 0.92, "borderline": 0.06, "deficient": 0.02},
                "cbc": {
                    "Haemoglobin": 14.5, "MCV": 88.0, "MCH": 29.5, "MCHC": 33.5,
                    "RDW_CV": 13.2, "WBC": 6.8, "Platelet": 245,
                    "Neutrophils": 58.0, "Lymphocytes": 32.0, "Monocytes": 6.0,
                    "Eosinophils": 3.0, "Basophils": 1.0, "LUC": 0.0,
                },
            },
            {
                "patient": "p002",
                "doctor": "d101",
                "risk_class": RiskClass.NORMAL,
                "label": "Normal",
                "probs": {"normal": 0.88, "borderline": 0.09, "deficient": 0.03},
                "cbc": {
                    "Haemoglobin": 13.2, "MCV": 86.5, "MCH": 28.8, "MCHC": 33.2,
                    "RDW_CV": 12.8, "WBC": 5.5, "Platelet": 280,
                    "Neutrophils": 55.0, "Lymphocytes": 35.0, "Monocytes": 5.5,
                    "Eosinophils": 3.5, "Basophils": 1.0, "LUC": 0.0,
                },
            },
            # Borderline (Class 2)
            {
                "patient": "p003",
                "doctor": "d102",
                "risk_class": RiskClass.BORDERLINE,
                "label": "Borderline",
                "probs": {"normal": 0.25, "borderline": 0.58, "deficient": 0.17},
                "cbc": {
                    "Haemoglobin": 12.8, "MCV": 96.0, "MCH": 32.5, "MCHC": 33.8,
                    "RDW_CV": 15.2, "WBC": 5.2, "Platelet": 198,
                    "Neutrophils": 52.0, "Lymphocytes": 38.0, "Monocytes": 6.0,
                    "Eosinophils": 3.0, "Basophils": 1.0, "LUC": 0.0,
                },
            },
            {
                "patient": "p004",
                "doctor": "d102",
                "risk_class": RiskClass.BORDERLINE,
                "label": "Borderline",
                "probs": {"normal": 0.18, "borderline": 0.62, "deficient": 0.20},
                "cbc": {
                    "Haemoglobin": 11.5, "MCV": 98.5, "MCH": 33.2, "MCHC": 33.5,
                    "RDW_CV": 16.1, "WBC": 4.8, "Platelet": 175,
                    "Neutrophils": 50.0, "Lymphocytes": 40.0, "Monocytes": 6.0,
                    "Eosinophils": 3.0, "Basophils": 1.0, "LUC": 0.0,
                },
            },
            # Deficient (Class 3)
            {
                "patient": "p005",
                "doctor": "d103",
                "risk_class": RiskClass.DEFICIENT,
                "label": "Deficient",
                "probs": {"normal": 0.05, "borderline": 0.15, "deficient": 0.80},
                "cbc": {
                    "Haemoglobin": 9.8, "MCV": 108.0, "MCH": 36.5, "MCHC": 33.8,
                    "RDW_CV": 18.5, "WBC": 3.5, "Platelet": 145,
                    "Neutrophils": 45.0, "Lymphocytes": 45.0, "Monocytes": 6.0,
                    "Eosinophils": 3.0, "Basophils": 1.0, "LUC": 0.0,
                },
            },
            {
                "patient": "p006",
                "doctor": "d103",
                "risk_class": RiskClass.DEFICIENT,
                "label": "Deficient",
                "probs": {"normal": 0.03, "borderline": 0.12, "deficient": 0.85},
                "cbc": {
                    "Haemoglobin": 10.2, "MCV": 105.5, "MCH": 35.8, "MCHC": 33.6,
                    "RDW_CV": 17.8, "WBC": 3.8, "Platelet": 158,
                    "Neutrophils": 48.0, "Lymphocytes": 42.0, "Monocytes": 6.0,
                    "Eosinophils": 3.0, "Basophils": 1.0, "LUC": 0.0,
                },
            },
        ]

        lab_user = users.get("lab_demo")
        created_count = 0

        for i, config in enumerate(screening_configs):
            screening_id = deterministic_uuid(
                DEMO_NAMESPACE, f"screening:{config['patient']}:{i}"
            )

            patient = patients[config["patient"]]
            doctor = doctors[config["doctor"]]

            # Calculate indices
            mcv = config["cbc"]["MCV"]
            mch = config["cbc"]["MCH"]
            rdw = config["cbc"]["RDW_CV"]

            indices = {
                "RI": round(mcv / (mch * 10) if mch > 0 else 0, 4),
                "MI": round(mcv * mcv * rdw / (100 * 10) if rdw > 0 else 0, 4),
                "Hb": config["cbc"]["Haemoglobin"],
            }

            # Generate hashes
            request_hash = hashlib.sha256(str(config["cbc"]).encode()).hexdigest()
            response_hash = hashlib.sha256(str(config["probs"]).encode()).hexdigest()
            screening_hash = hashlib.sha256(
                f"{request_hash}{response_hash}".encode()
            ).hexdigest()

            screening, created = Screening.objects.update_or_create(
                id=screening_id,
                defaults={
                    "patient": patient,
                    "lab": lab,
                    "doctor": doctor,
                    "performed_by": lab_user.username if lab_user else "system",
                    "risk_class": config["risk_class"],
                    "label_text": config["label"],
                    "probabilities": config["probs"],
                    "rules_fired": [],
                    "cbc_snapshot": config["cbc"],
                    "indices": indices,
                    "model_version": "v3.0.0-demo",
                    "model_artifact_hash": hashlib.sha256(b"demo-model").hexdigest(),
                    "request_hash": request_hash,
                    "response_hash": response_hash,
                    "screening_hash": screening_hash,
                },
            )

            if created:
                created_count += 1

        self.stdout.write(f"  Created {created_count} screenings")

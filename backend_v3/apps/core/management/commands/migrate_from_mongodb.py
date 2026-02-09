"""
Management command for migrating data from MongoDB (v1) to PostgreSQL (v3).

Usage:
    python manage.py migrate_from_mongodb --mongodb-uri "mongodb://localhost:27017/biosaas"
    python manage.py migrate_from_mongodb --dry-run  # Preview without writing

Requirements:
    - MongoDB must be accessible
    - v3 database must have migrations applied
    - MASTER_ENCRYPTION_KEY must match the v1 key for PHI migration
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone as tz

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django_tenants.utils import schema_context

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Migrate data from MongoDB (v1) to PostgreSQL (v3)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--mongodb-uri",
            default="mongodb://localhost:27017/biosaas",
            help="MongoDB connection URI (default: mongodb://localhost:27017/biosaas)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview migration without writing to database",
        )
        parser.add_argument(
            "--skip-screenings",
            action="store_true",
            help="Skip migrating screenings (large dataset)",
        )
        parser.add_argument(
            "--org-filter",
            help="Migrate only a specific organization ID",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Batch size for bulk operations (default: 100)",
        )

    def handle(self, *args, **options):
        try:
            from pymongo import MongoClient
        except ImportError:
            raise CommandError(
                "pymongo is required for migration. "
                "Install it with: pip install pymongo"
            )

        # Import Django models
        from apps.core.crypto import encrypt_field, is_crypto_ready
        from apps.core.models import (
            AuditLogEntry,
            Domain,
            MFASettings,
            Organization,
            RefreshToken,
            Role,
            User,
        )
        from apps.screening.models import (
            Consent,
            Doctor,
            Lab,
            Patient,
            RiskClass,
            Screening,
        )

        if not is_crypto_ready():
            raise CommandError(
                "MASTER_ENCRYPTION_KEY not configured. "
                "Ensure it matches the v1 key for PHI migration."
            )

        mongodb_uri = options["mongodb_uri"]
        dry_run = options["dry_run"]
        skip_screenings = options["skip_screenings"]
        org_filter = options["org_filter"]
        batch_size = options["batch_size"]

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN MODE - No changes will be made")
            )

        # Connect to MongoDB
        self.stdout.write(f"Connecting to MongoDB: {mongodb_uri}")
        try:
            client = MongoClient(mongodb_uri)
            db = client.get_default_database()
            # Test connection
            db.list_collection_names()
            self.stdout.write(self.style.SUCCESS("Connected to MongoDB"))
        except Exception as e:
            raise CommandError(f"Failed to connect to MongoDB: {e}")

        # Migration statistics
        stats = {
            "organizations": 0,
            "users": 0,
            "labs": 0,
            "doctors": 0,
            "patients": 0,
            "screenings": 0,
            "consents": 0,
            "errors": 0,
        }

        # Step 1: Migrate Organizations
        self.stdout.write("\n--- Migrating Organizations ---")
        orgs_map = {}  # MongoDB orgId -> Django Organization

        # Get unique organizations from labs collection
        org_ids = db.labs.distinct("orgId")
        if org_filter:
            org_ids = [oid for oid in org_ids if str(oid) == org_filter]

        for org_id in org_ids:
            if not org_id:
                continue

            # Get org details from first lab
            sample_lab = db.labs.find_one({"orgId": org_id})
            org_name = f"Organization {org_id}"
            tier = "standard"

            if sample_lab:
                tier = sample_lab.get("tier", "standard")

            schema_name = f"org_{str(org_id).replace('-', '_')[:20]}"

            if not dry_run:
                org, created = Organization.objects.update_or_create(
                    schema_name=schema_name,
                    defaults={
                        "name": org_name,
                        "tier": tier,
                        "is_active": True,
                    },
                )

                # Create default domain
                Domain.objects.update_or_create(
                    tenant=org,
                    defaults={
                        "domain": f"{schema_name}.localhost",
                        "is_primary": True,
                    },
                )

                orgs_map[str(org_id)] = org
                stats["organizations"] += 1
                self.stdout.write(f"  Organization: {org_name} (schema: {schema_name})")
            else:
                self.stdout.write(f"  [DRY-RUN] Organization: {org_name}")

        # Step 2: Migrate Users
        self.stdout.write("\n--- Migrating Users ---")
        users_map = {}  # MongoDB username -> Django User

        mongo_users = db.users.find({})
        for mongo_user in mongo_users:
            username = mongo_user.get("username")
            org_id = str(mongo_user.get("orgId", ""))

            if org_filter and org_id != org_filter:
                continue

            role_map = {
                "ADMIN": Role.ADMIN,
                "LAB": Role.LAB,
                "DOCTOR": Role.DOCTOR,
            }
            role = role_map.get(mongo_user.get("role", "LAB"), Role.LAB)

            if not dry_run:
                org = orgs_map.get(org_id)
                if not org and org_id:
                    # Create org if not exists
                    schema_name = f"org_{org_id.replace('-', '_')[:20]}"
                    org, _ = Organization.objects.get_or_create(
                        schema_name=schema_name,
                        defaults={"name": f"Organization {org_id}", "tier": "standard"},
                    )
                    orgs_map[org_id] = org

                user, created = User.objects.update_or_create(
                    username=username,
                    defaults={
                        "email": mongo_user.get("email", ""),
                        "name": mongo_user.get("name", ""),
                        "role": role,
                        "organization": org,
                        "is_active": mongo_user.get("isActive", True),
                        "is_staff": role == Role.ADMIN,
                    },
                )

                # Set password hash directly if available (same bcrypt format)
                if mongo_user.get("passwordHash"):
                    user.password = mongo_user["passwordHash"]
                    user.save()

                users_map[username] = user
                stats["users"] += 1

                if created:
                    self.stdout.write(f"  Created user: {username}")
            else:
                self.stdout.write(f"  [DRY-RUN] User: {username}")

        # Step 3: Migrate Labs, Doctors, Patients, Screenings per Organization
        for org_id, org in orgs_map.items():
            self.stdout.write(f"\n--- Migrating data for {org.name} ---")

            if not dry_run:
                with schema_context(org.schema_name):
                    # Migrate Labs
                    self._migrate_labs(db, org_id, stats, dry_run, batch_size)

                    # Migrate Doctors
                    self._migrate_doctors(db, org_id, stats, dry_run, batch_size)

                    # Migrate Patients
                    self._migrate_patients(db, org_id, stats, dry_run, batch_size)

                    # Migrate Screenings
                    if not skip_screenings:
                        self._migrate_screenings(
                            db, org_id, users_map, stats, dry_run, batch_size
                        )

                    # Migrate Consents
                    self._migrate_consents(db, org_id, stats, dry_run, batch_size)

        # Print summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("Migration Summary"))
        self.stdout.write("=" * 50)
        for key, value in stats.items():
            self.stdout.write(f"  {key}: {value}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\nDRY RUN - No changes were made to the database")
            )

        # Close MongoDB connection
        client.close()

    def _migrate_labs(self, db, org_id, stats, dry_run, batch_size):
        """Migrate labs for an organization."""
        from apps.screening.models import Lab

        labs = db.labs.find({"orgId": org_id})
        labs_map = {}

        for mongo_lab in labs:
            lab_code = mongo_lab.get("id") or mongo_lab.get("code")
            if not lab_code:
                continue

            if not dry_run:
                lab, created = Lab.objects.update_or_create(
                    code=lab_code,
                    defaults={
                        "name": mongo_lab.get("name", lab_code),
                        "tier": mongo_lab.get("tier", "standard"),
                        "address": mongo_lab.get("address", ""),
                        "contact_email": mongo_lab.get("email", ""),
                        "is_active": True,
                    },
                )
                labs_map[lab_code] = lab
                stats["labs"] += 1

                if created:
                    self.stdout.write(f"    Lab: {lab.name}")

        return labs_map

    def _migrate_doctors(self, db, org_id, stats, dry_run, batch_size):
        """Migrate doctors for an organization."""
        from apps.screening.models import Doctor, Lab

        doctors = db.doctors.find({"orgId": org_id})
        doctors_map = {}

        for mongo_doc in doctors:
            doc_code = mongo_doc.get("id") or mongo_doc.get("code")
            if not doc_code:
                continue

            lab_code = mongo_doc.get("labId")
            lab = None
            if lab_code:
                lab = Lab.objects.filter(code=lab_code).first()

            if not lab:
                # Try to get first lab
                lab = Lab.objects.first()

            if not dry_run and lab:
                doctor, created = Doctor.objects.update_or_create(
                    code=doc_code,
                    defaults={
                        "name": mongo_doc.get("name", doc_code),
                        "department": mongo_doc.get("department", ""),
                        "specialization": mongo_doc.get("specialization", ""),
                        "lab": lab,
                        "email": mongo_doc.get("email", ""),
                        "is_active": True,
                    },
                )
                doctors_map[doc_code] = doctor
                stats["doctors"] += 1

                if created:
                    self.stdout.write(f"    Doctor: {doctor.name}")

        return doctors_map

    def _migrate_patients(self, db, org_id, stats, dry_run, batch_size):
        """Migrate patients for an organization."""
        from apps.screening.models import Doctor, Lab, Patient

        patients = db.patients.find({"orgId": org_id})
        patients_map = {}

        for mongo_patient in patients:
            patient_id = mongo_patient.get("patientId") or mongo_patient.get("id")
            if not patient_id:
                continue

            lab_code = mongo_patient.get("labId")
            lab = Lab.objects.filter(code=lab_code).first() if lab_code else Lab.objects.first()

            if not lab:
                continue

            doctor_code = mongo_patient.get("doctorId")
            doctor = Doctor.objects.filter(code=doctor_code).first() if doctor_code else None

            if not dry_run:
                # PHI: name_encrypted should already be encrypted with same key
                name_encrypted = mongo_patient.get("nameEncrypted", "")
                if not name_encrypted:
                    # Fallback: encrypt plain name if present
                    from apps.core.crypto import encrypt_field
                    plain_name = mongo_patient.get("name", "Unknown")
                    name_encrypted = encrypt_field(plain_name)

                patient, created = Patient.objects.update_or_create(
                    patient_id=patient_id,
                    defaults={
                        "name_encrypted": name_encrypted,
                        "age": mongo_patient.get("age", 0),
                        "sex": mongo_patient.get("sex", "M")[:1].upper(),
                        "lab": lab,
                        "referring_doctor": doctor,
                    },
                )
                patients_map[patient_id] = patient
                stats["patients"] += 1

                if created:
                    self.stdout.write(f"    Patient: {patient_id}")

        return patients_map

    def _migrate_screenings(self, db, org_id, users_map, stats, dry_run, batch_size):
        """Migrate screenings for an organization."""
        from apps.screening.models import Doctor, Lab, Patient, RiskClass, Screening

        # Risk class mapping
        risk_map = {
            1: RiskClass.NORMAL,
            2: RiskClass.BORDERLINE,
            3: RiskClass.DEFICIENT,
            "normal": RiskClass.NORMAL,
            "borderline": RiskClass.BORDERLINE,
            "deficient": RiskClass.DEFICIENT,
        }

        screenings = db.screenings.find({"orgId": org_id})
        count = 0

        for mongo_screening in screenings:
            patient_id = mongo_screening.get("patientId")
            if not patient_id:
                continue

            patient = Patient.objects.filter(patient_id=patient_id).first()
            if not patient:
                continue

            lab_code = mongo_screening.get("labId")
            lab = Lab.objects.filter(code=lab_code).first() if lab_code else patient.lab

            doctor_code = mongo_screening.get("doctorId")
            doctor = Doctor.objects.filter(code=doctor_code).first() if doctor_code else None

            # Map risk class
            raw_risk = mongo_screening.get("riskClass", mongo_screening.get("prediction", 1))
            risk_class = risk_map.get(raw_risk, RiskClass.NORMAL)

            if not dry_run:
                # Generate unique ID from MongoDB _id
                mongo_id = str(mongo_screening.get("_id", uuid.uuid4()))
                screening_uuid = uuid.UUID(hashlib.sha256(mongo_id.encode()).hexdigest()[:32])

                screening, created = Screening.objects.update_or_create(
                    id=screening_uuid,
                    defaults={
                        "patient": patient,
                        "lab": lab,
                        "doctor": doctor,
                        "performed_by": mongo_screening.get("performedBy", "system"),
                        "risk_class": risk_class,
                        "label_text": mongo_screening.get("labelText", str(risk_class.label)),
                        "probabilities": mongo_screening.get("probabilities", {}),
                        "rules_fired": mongo_screening.get("rulesFired", []),
                        "cbc_snapshot": mongo_screening.get("cbcSnapshot", mongo_screening.get("cbc", {})),
                        "indices": mongo_screening.get("indices", {}),
                        "model_version": mongo_screening.get("modelVersion", "v1-migrated"),
                        "model_artifact_hash": mongo_screening.get("modelHash", ""),
                        "request_hash": mongo_screening.get("requestHash", ""),
                        "response_hash": mongo_screening.get("responseHash", ""),
                        "screening_hash": mongo_screening.get("screeningHash", ""),
                        "consent_id": mongo_screening.get("consentId"),
                    },
                )

                if created:
                    count += 1
                    stats["screenings"] += 1

                    if count % batch_size == 0:
                        self.stdout.write(f"    Screenings migrated: {count}")

        self.stdout.write(f"    Total screenings: {count}")

    def _migrate_consents(self, db, org_id, stats, dry_run, batch_size):
        """Migrate consents for an organization."""
        from apps.screening.models import Consent, Patient

        consents = db.consents.find({"orgId": org_id})
        count = 0

        for mongo_consent in consents:
            patient_id = mongo_consent.get("patientId")
            if not patient_id:
                continue

            patient = Patient.objects.filter(patient_id=patient_id).first()
            if not patient:
                continue

            if not dry_run:
                mongo_id = str(mongo_consent.get("_id", uuid.uuid4()))
                consent_uuid = uuid.UUID(hashlib.sha256(mongo_id.encode()).hexdigest()[:32])

                # Parse timestamp
                consented_at = mongo_consent.get("consentedAt")
                if isinstance(consented_at, str):
                    try:
                        consented_at = datetime.fromisoformat(consented_at.replace("Z", "+00:00"))
                    except ValueError:
                        consented_at = timezone.now()
                elif not consented_at:
                    consented_at = timezone.now()

                consent, created = Consent.objects.update_or_create(
                    id=consent_uuid,
                    defaults={
                        "patient": patient,
                        "consent_type": mongo_consent.get("consentType", "screening"),
                        "consent_text": mongo_consent.get("consentText", ""),
                        "consented_by": mongo_consent.get("consentedBy", "system"),
                        "consent_method": mongo_consent.get("consentMethod", "verbal"),
                        "status": mongo_consent.get("status", "active"),
                        "consented_at": consented_at,
                    },
                )

                if created:
                    count += 1
                    stats["consents"] += 1

        self.stdout.write(f"    Total consents: {count}")

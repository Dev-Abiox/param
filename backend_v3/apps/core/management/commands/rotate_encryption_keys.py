"""
Management command to re-encrypt all PHI fields under the current primary key.

Usage:
    python manage.py rotate_encryption_keys              # dry-run (default)
    python manage.py rotate_encryption_keys --apply       # actually re-encrypt
    python manage.py rotate_encryption_keys --batch=500   # custom batch size

After running with --apply and verifying success, remove old keys from
PREVIOUS_ENCRYPTION_KEYS and restart services.
"""

from django.core.management.base import BaseCommand
from django.db import connection

from django_tenants.utils import get_tenant_model, tenant_context

from apps.core.crypto import CryptoError, rotate_field


class Command(BaseCommand):
    help = 'Re-encrypt all PHI fields under the current MASTER_ENCRYPTION_KEY.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            default=False,
            help='Actually perform re-encryption. Without this flag, runs in dry-run mode.',
        )
        parser.add_argument(
            '--batch',
            type=int,
            default=200,
            help='Number of records to process per batch (default: 200).',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        batch_size = options['batch']
        mode = 'APPLY' if apply else 'DRY-RUN'
        self.stdout.write(f'\n=== Key Rotation ({mode}) ===\n')

        TenantModel = get_tenant_model()
        tenants = TenantModel.objects.exclude(schema_name='public')

        total_rotated = 0
        total_skipped = 0
        total_errors = 0

        for tenant in tenants:
            self.stdout.write(f'\nTenant: {tenant.schema_name}')
            with tenant_context(tenant):
                rotated, skipped, errors = self._rotate_patients(apply, batch_size)
                total_rotated += rotated
                total_skipped += skipped
                total_errors += errors

        self.stdout.write(
            f'\n=== Summary ===\n'
            f'  Rotated: {total_rotated}\n'
            f'  Skipped (already current): {total_skipped}\n'
            f'  Errors:  {total_errors}\n'
        )
        if not apply and total_rotated > 0:
            self.stdout.write(
                self.style.WARNING('Dry-run complete. Re-run with --apply to commit changes.')
            )

    def _rotate_patients(self, apply: bool, batch_size: int) -> tuple[int, int, int]:
        from apps.screening.models import Patient

        rotated = 0
        skipped = 0
        errors = 0

        patients = Patient.objects.all().only(
            'id', 'name_encrypted', 'age_encrypted', 'sex_encrypted',
        ).iterator(chunk_size=batch_size)

        for patient in patients:
            try:
                changed = False
                for field in ('name_encrypted', 'age_encrypted', 'sex_encrypted'):
                    value = getattr(patient, field) or ''
                    if not value:
                        continue
                    new_value = rotate_field(value)
                    if new_value is not None:
                        if apply:
                            setattr(patient, field, new_value)
                        changed = True

                if changed:
                    if apply:
                        patient.save(update_fields=['name_encrypted', 'age_encrypted', 'sex_encrypted'])
                    rotated += 1
                else:
                    skipped += 1
            except CryptoError as e:
                errors += 1
                self.stderr.write(f'  ERROR: Patient {patient.id}: {e}')

        self.stdout.write(f'  rotated={rotated} skipped={skipped} errors={errors}')
        return rotated, skipped, errors

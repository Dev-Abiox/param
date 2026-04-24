"""One-shot backfill for P0-4 — re-encrypts legacy plaintext rows
under the Fernet primary key.

Handles the two columns that the P0-4 migrations switched to
Fernet-at-rest but deliberately did not auto-backfill during
``migrate_schemas`` (see docstrings on ``billing/0008`` and
``screening/0012``):

  - ``WebhookEndpoint.secret`` (shared schema)
  - ``Screening.cbc_snapshot``  (tenant schemas — iterates all tenants)

Safe to run multiple times.  Each row is inspected first — already-
ciphertext rows are skipped.  A single bad row does not abort the
whole run.  Progress and per-row failures are printed.

Usage
-----

Dry-run (no writes, just reports what would change)::

    python manage.py encrypt_plaintext_columns --dry-run

Backfill webhook secrets only (shared schema, fast)::

    python manage.py encrypt_plaintext_columns --webhook-secrets

Backfill Screening.cbc_snapshot across every tenant schema
(slow — re-runs on each tenant; prefer a maintenance window)::

    python manage.py encrypt_plaintext_columns --cbc-snapshots

All of the above::

    python manage.py encrypt_plaintext_columns --all
"""

from __future__ import annotations

import sys
import time
from typing import Callable

from django.core.management.base import BaseCommand
from django.db import transaction
from django_tenants.utils import get_tenant_model, schema_context


class Command(BaseCommand):
    help = (
        'Backfill the P0-4 encrypted columns — WebhookEndpoint.secret and '
        'Screening.cbc_snapshot — for rows that still hold legacy plaintext.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--webhook-secrets', action='store_true',
            help='Re-encrypt WebhookEndpoint.secret rows still in plaintext.',
        )
        parser.add_argument(
            '--cbc-snapshots', action='store_true',
            help='Encrypt Screening.cbc_snapshot into cbc_snapshot_enc '
                 'and populate age_bucket + sex_code, per tenant.',
        )
        parser.add_argument(
            '--all', action='store_true',
            help='Shortcut for --webhook-secrets --cbc-snapshots.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would be re-encrypted without writing.',
        )
        parser.add_argument(
            '--tenant-schema', default=None,
            help='Limit CBC backfill to a single tenant schema name '
                 '(defaults to every tenant).',
        )

    def handle(self, *args, **opts):
        do_webhook = opts['webhook_secrets'] or opts['all']
        do_cbc = opts['cbc_snapshots'] or opts['all']
        if not (do_webhook or do_cbc):
            self.stderr.write(self.style.ERROR(
                'Nothing to do.  Pass --webhook-secrets, --cbc-snapshots, or --all.'
            ))
            sys.exit(2)

        dry_run = opts['dry_run']
        single_tenant = opts['tenant_schema']

        if do_webhook:
            self._run_webhook_secrets(dry_run=dry_run)

        if do_cbc:
            self._run_cbc_snapshots(dry_run=dry_run, single_tenant=single_tenant)

    # ── WebhookEndpoint.secret (shared schema) ────────────────────────
    def _run_webhook_secrets(self, dry_run: bool) -> None:
        from apps.billing.models import WebhookEndpoint
        from apps.core.crypto import encrypt_field
        from apps.core.fields import _looks_like_fernet_token

        self.stdout.write(self.style.MIGRATE_HEADING(
            '\n[webhook_secrets] scanning WebhookEndpoint rows in public schema'
        ))
        examined = 0
        encrypted = 0
        skipped = 0
        failed = 0
        t0 = time.time()

        for row in WebhookEndpoint.objects.all().only('id', 'secret').iterator(chunk_size=500):
            examined += 1
            secret = row.secret
            if not secret:
                skipped += 1
                continue
            if _looks_like_fernet_token(secret):
                skipped += 1
                continue
            if dry_run:
                encrypted += 1
                continue
            try:
                with transaction.atomic():
                    row.secret = encrypt_field(secret)
                    row.save(update_fields=['secret'])
                encrypted += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.stderr.write(self.style.ERROR(
                    f'  WebhookEndpoint id={row.id} failed: {exc}'
                ))

        self.stdout.write(self.style.SUCCESS(
            f'[webhook_secrets] examined={examined} '
            f'encrypted={encrypted} skipped={skipped} failed={failed} '
            f'took={time.time()-t0:.1f}s '
            f'{"(DRY-RUN)" if dry_run else ""}'
        ))

    # ── Screening.cbc_snapshot (tenant schemas) ───────────────────────
    def _run_cbc_snapshots(self, dry_run: bool, single_tenant: str | None) -> None:
        Tenant = get_tenant_model()
        tenants = Tenant.objects.exclude(schema_name='public')
        if single_tenant:
            tenants = tenants.filter(schema_name=single_tenant)

        total_examined = 0
        total_encrypted = 0
        total_skipped = 0
        total_failed = 0
        t0 = time.time()

        for tenant in tenants.iterator():
            examined, encrypted, skipped, failed = self._backfill_cbc_for_tenant(
                tenant.schema_name, dry_run=dry_run,
            )
            total_examined += examined
            total_encrypted += encrypted
            total_skipped += skipped
            total_failed += failed

        self.stdout.write(self.style.SUCCESS(
            f'\n[cbc_snapshots/overall] examined={total_examined} '
            f'encrypted={total_encrypted} skipped={total_skipped} '
            f'failed={total_failed} took={time.time()-t0:.1f}s '
            f'{"(DRY-RUN)" if dry_run else ""}'
        ))

    def _backfill_cbc_for_tenant(self, schema_name: str, dry_run: bool) -> tuple[int, int, int, int]:
        from apps.screening.models import Screening, age_bucket_for, sex_code_for

        examined = encrypted = skipped = failed = 0

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n[cbc_snapshots] tenant={schema_name}'
        ))
        with schema_context(schema_name):
            qs = Screening.objects.all().only(
                'id', 'cbc_snapshot', 'cbc_snapshot_enc',
                'age_bucket', 'sex_code',
            )
            for row in qs.iterator(chunk_size=500):
                examined += 1
                legacy = row.cbc_snapshot or {}
                if not legacy:
                    skipped += 1
                    continue
                if row.cbc_snapshot_enc and row.age_bucket and row.sex_code:
                    skipped += 1
                    continue
                if dry_run:
                    encrypted += 1
                    continue
                try:
                    with transaction.atomic():
                        if not row.cbc_snapshot_enc:
                            row.cbc_snapshot_enc = legacy
                        if not row.age_bucket:
                            row.age_bucket = age_bucket_for(
                                legacy.get('Age', legacy.get('age')),
                            )
                        if not row.sex_code:
                            row.sex_code = sex_code_for(
                                legacy.get('Sex', legacy.get('sex')),
                            )
                        row.cbc_snapshot = {}
                        row.save(update_fields=[
                            'cbc_snapshot', 'cbc_snapshot_enc',
                            'age_bucket', 'sex_code',
                        ])
                    encrypted += 1
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    self.stderr.write(self.style.ERROR(
                        f'  Screening id={row.id} in {schema_name} failed: {exc}'
                    ))

        self.stdout.write(
            f'  examined={examined} encrypted={encrypted} '
            f'skipped={skipped} failed={failed}'
        )
        return examined, encrypted, skipped, failed

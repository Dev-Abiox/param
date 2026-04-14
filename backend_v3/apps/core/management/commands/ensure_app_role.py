"""
ensure_app_role — provision a least-privilege Postgres role for the
Django backend at runtime.

The platform runs two DB identities:

    clinomic_migrator   — owns schemas and every object inside them,
                          used by `migrate_schemas` and by any admin
                          operation that issues DDL.

    clinomic_app        — CRUD-only. Used by the uvicorn workers.
                          No CREATE, no DROP, no ALTER — so a
                          compromised request handler can't rewrite
                          the schema.

This command is idempotent: it creates the app role if missing,
resets its password from env, grants SELECT/INSERT/UPDATE/DELETE
on every existing schema and table, and registers default
privileges so any table the migrator creates in the future is
automatically readable/writable by the app role.

Run it from the deploy pipeline after migrate_schemas:

    env POSTGRES_USER=$POSTGRES_MIGRATOR_USER \
        POSTGRES_PASSWORD=$POSTGRES_MIGRATOR_PASSWORD \
        python manage.py migrate_schemas --noinput
    env POSTGRES_USER=$POSTGRES_MIGRATOR_USER \
        POSTGRES_PASSWORD=$POSTGRES_MIGRATOR_PASSWORD \
        python manage.py ensure_app_role

New tenant schemas created on-demand (when a SUPER_ADMIN provisions
an organisation) are handled by the post_schema_sync signal in
apps/core/signals.py — no manual grant step needed.

Safe to skip entirely: if POSTGRES_APP_USER is not set in env, the
command is a no-op and the backend continues to run as the migrator
role the way it has since day one.
"""

import os

from django.core.management.base import BaseCommand
from django.db import connection


def _quote_ident(ident: str) -> str:
    """Minimal identifier quoting for role/schema names we generate."""
    safe = ''.join(c for c in ident if c.isalnum() or c == '_')
    if safe != ident or not safe:
        raise ValueError(f"Refusing to use identifier with special chars: {ident!r}")
    return f'"{safe}"'


class Command(BaseCommand):
    help = 'Create / refresh the least-privilege app role (idempotent).'

    def handle(self, *args, **options):
        app_user = os.environ.get('POSTGRES_APP_USER', '').strip()
        app_pass = os.environ.get('POSTGRES_APP_PASSWORD', '').strip()

        if not app_user:
            self.stdout.write(
                'POSTGRES_APP_USER is empty — skipping. Set it in env to '
                'enable the least-privilege split.'
            )
            return
        if not app_pass:
            self.stderr.write(
                'POSTGRES_APP_USER is set but POSTGRES_APP_PASSWORD is empty. '
                'Refusing to create a role with no password.'
            )
            return

        user_ident = _quote_ident(app_user)

        # Literal password — we escape single quotes by doubling them,
        # which is the standard SQL escape. Not using parameterised
        # query because CREATE ROLE doesn't accept placeholders.
        pass_literal = "'" + app_pass.replace("'", "''") + "'"

        with connection.cursor() as cursor:
            # 1. Create role if it doesn't exist; always (re)set the password.
            cursor.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", [app_user]
            )
            exists = cursor.fetchone() is not None
            if not exists:
                cursor.execute(
                    f"CREATE ROLE {user_ident} LOGIN PASSWORD {pass_literal} "
                    f"NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT"
                )
                self.stdout.write(f'created role {app_user}')
            else:
                cursor.execute(f"ALTER ROLE {user_ident} WITH PASSWORD {pass_literal}")
                self.stdout.write(f'role {app_user} already existed; refreshed password')

            # 2. Enumerate every schema the backend touches (public + all
            #    django-tenants schemas) and grant USAGE + CRUD on the
            #    existing objects inside them.
            cursor.execute(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name NOT IN ('information_schema', 'pg_catalog', 'pg_toast') "
                "  AND schema_name NOT LIKE 'pg_temp_%' "
                "  AND schema_name NOT LIKE 'pg_toast_temp_%'"
            )
            schemas = [row[0] for row in cursor.fetchall()]

            grant_count = 0
            for schema in schemas:
                try:
                    s_ident = _quote_ident(schema)
                except ValueError:
                    self.stderr.write(f'skipping schema with unsafe name: {schema!r}')
                    continue

                cursor.execute(f"GRANT USAGE ON SCHEMA {s_ident} TO {user_ident}")
                cursor.execute(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES, TRIGGER "
                    f"ON ALL TABLES IN SCHEMA {s_ident} TO {user_ident}"
                )
                cursor.execute(
                    f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES "
                    f"IN SCHEMA {s_ident} TO {user_ident}"
                )

                # Default privileges: anything created by the CURRENT role
                # (the migrator) in this schema from now on is automatically
                # granted to the app user. This is how new tables added by
                # future migrations become readable without re-running grants.
                cursor.execute(
                    f"ALTER DEFAULT PRIVILEGES IN SCHEMA {s_ident} "
                    f"GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES, TRIGGER "
                    f"ON TABLES TO {user_ident}"
                )
                cursor.execute(
                    f"ALTER DEFAULT PRIVILEGES IN SCHEMA {s_ident} "
                    f"GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {user_ident}"
                )
                grant_count += 1

            self.stdout.write(
                f'granted CRUD on {grant_count} schema(s) to {app_user}'
            )

"""
Signal handlers that keep the least-privilege Postgres app role in sync
with the django-tenants schema graph.

django-tenants fires `post_schema_sync` after a new tenant schema has
been created and migrated. At that point the schema exists and is
owned by whichever DB role ran the migration (normally the migrator).
The app role needs USAGE on the schema plus CRUD on its tables before
any API request can touch the new tenant — otherwise the first request
blows up with "permission denied for schema".

When POSTGRES_APP_USER is unset (the legacy single-role configuration),
this handler is a complete no-op. So it's safe to land before flipping
the least-privilege switch in env.
"""

import logging
import os

from django.db import connection

logger = logging.getLogger(__name__)


def _safe_ident(ident: str) -> str | None:
    """Whitelist-reject identifiers that would be unsafe to interpolate."""
    if not ident:
        return None
    if not all(c.isalnum() or c == '_' for c in ident):
        return None
    return f'"{ident}"'


def grant_new_tenant_schema(sender, tenant, **kwargs):
    """
    Signal receiver: called by django-tenants after a new tenant schema
    has been migrated. Grants the app role access to the newly-created
    schema and its tables.

    sender: the tenant model class (Organization)
    tenant: the Organization instance whose schema was just synced
    """
    app_user = os.environ.get('POSTGRES_APP_USER', '').strip()
    if not app_user:
        return  # single-role mode — nothing to do

    user_ident = _safe_ident(app_user)
    schema_ident = _safe_ident(getattr(tenant, 'schema_name', None))
    if not user_ident or not schema_ident:
        logger.warning(
            'grant_new_tenant_schema: refusing unsafe identifier '
            '(user=%r, schema=%r)',
            app_user, getattr(tenant, 'schema_name', None),
        )
        return

    try:
        with connection.cursor() as cursor:
            cursor.execute(f"GRANT USAGE ON SCHEMA {schema_ident} TO {user_ident}")
            cursor.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES, TRIGGER "
                f"ON ALL TABLES IN SCHEMA {schema_ident} TO {user_ident}"
            )
            cursor.execute(
                f"GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES "
                f"IN SCHEMA {schema_ident} TO {user_ident}"
            )
            cursor.execute(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_ident} "
                f"GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES, TRIGGER "
                f"ON TABLES TO {user_ident}"
            )
            cursor.execute(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_ident} "
                f"GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {user_ident}"
            )
        logger.info(
            'granted app-user CRUD on new tenant schema %s',
            getattr(tenant, 'schema_name', None),
        )
    except Exception:
        # Never crash a tenant-create on a grant failure — log loudly
        # and let ops re-run `ensure_app_role` to backfill.
        logger.exception(
            'failed to grant app-user access to new schema %s — '
            'run ensure_app_role to backfill',
            getattr(tenant, 'schema_name', None),
        )


def connect_signals():
    """Wire up all module-level signal receivers. Called from AppConfig.ready."""
    try:
        from django_tenants.signals import post_schema_sync
    except ImportError:
        logger.warning('django_tenants.signals.post_schema_sync not importable; '
                       'new-tenant grants will rely on the periodic ensure_app_role pass')
        return
    post_schema_sync.connect(grant_new_tenant_schema)

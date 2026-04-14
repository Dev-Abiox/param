# Postgres least-privilege cutover

## Why

`POSTGRES_USER` (default `clinomic_user`) owns every schema and every
table. It can `CREATE`, `DROP`, `ALTER`, and `TRUNCATE` anything. If
an attacker ever finds a SQL-injection hole in an ORM call, that's
the identity they'll be running as.

This split gives the backend workers a CRUD-only identity while
keeping a separate privileged identity for `migrate_schemas` and
platform admin DDL.

```
clinomic_migrator  →  owns schemas + tables, runs migrations
clinomic_app       →  SELECT/INSERT/UPDATE/DELETE only
```

`migrate_schemas` continues to run as the migrator during deploy.
uvicorn runs as the app user.

## Current state

The infrastructure has shipped (commits `<this sprint>`), but the
backend still runs as `POSTGRES_USER` by default — cutover is an
opt-in env-var change. Status of each piece:

- [x] `ensure_app_role` management command — creates the role,
      resets its password from env, grants CRUD on every existing
      schema, installs default privileges for future tables.
      Idempotent. Runs automatically on every compose up via the
      backend's startup command.
- [x] `apps.core.signals.grant_new_tenant_schema` — receives
      `post_schema_sync` from django-tenants so new tenant schemas
      get CRUD grants for the app user the moment they're created
      (not on the next deploy).
- [x] `POSTGRES_APP_USER` / `POSTGRES_APP_PASSWORD` documented in
      `backend_v3/.env.example`.
- [ ] `POSTGRES_USER` in prod env is still pointed at the migrator
      credentials. The backend therefore still runs as the migrator.
      **This is the switch.**

## Cutover procedure

Do this during a low-traffic window. Rollback is a single env-var
change + container recreate, so it's reversible in under a minute.

### 1. Add the new role credentials to the prod env file

On the server, append to `/opt/clinomic-b12-platform/.env`:

```bash
POSTGRES_APP_USER=clinomic_app
POSTGRES_APP_PASSWORD=<generate with: python -c "import secrets; print(secrets.token_urlsafe(32))">
```

Do **not** touch `POSTGRES_USER` / `POSTGRES_PASSWORD` yet. The
backend is still running as migrator. Save the file.

### 2. Recreate the backend container

```bash
cd /opt/clinomic-b12-platform
docker compose -f docker-compose.prod.yml up -d --force-recreate backend
```

On startup the compose command runs
`python manage.py ensure_app_role`. Because `POSTGRES_APP_USER` is
now set, the command creates `clinomic_app`, sets its password,
and grants CRUD on every existing schema.

Verify the role was created:

```bash
docker exec clinomic-b12-platform-db-1 \
  psql -U clinomic_user -d clinomic -c "\\du clinomic_app"
```

You should see a row with `Cannot login = false`, no superuser,
no createdb, no createrole.

### 3. Verify grants on a representative schema

```bash
docker exec clinomic-b12-platform-db-1 \
  psql -U clinomic_user -d clinomic -c "
SELECT grantee, privilege_type
FROM information_schema.table_privileges
WHERE table_schema = 'public' AND grantee = 'clinomic_app'
ORDER BY table_name, privilege_type LIMIT 20;
"
```

Expected: `SELECT/INSERT/UPDATE/DELETE` rows on the shared
`core_user`, `core_organization`, `billing_*`, etc. No
`CREATE/DROP/REFERENCES` beyond what we granted.

### 4. Flip the switch

Edit `/opt/clinomic-b12-platform/.env`:

```bash
# Rename the existing privileged identity so compose migrations keep
# using it, and point the runtime vars at the new app role.
POSTGRES_MIGRATOR_USER=clinomic_user
POSTGRES_MIGRATOR_PASSWORD=<existing clinomic_user password>

POSTGRES_USER=clinomic_app
POSTGRES_PASSWORD=<the token_urlsafe you generated in step 1>
```

Then recreate:

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate backend
```

The compose startup command needs to be updated to run migrations
under the migrator identity — see the next section.

### 5. Update the compose command (one-time)

`docker-compose.prod.yml` currently runs `migrate_schemas` as the
default env's `POSTGRES_USER`. After step 4 that's the app user,
which will fail on `CREATE SCHEMA`.

Change the backend `command:` to:

```yaml
command: >
  sh -euc "
  python manage.py collectstatic --noinput &&
  env POSTGRES_USER=\"$$POSTGRES_MIGRATOR_USER\" POSTGRES_PASSWORD=\"$$POSTGRES_MIGRATOR_PASSWORD\"
      python manage.py migrate_schemas --noinput &&
  env POSTGRES_USER=\"$$POSTGRES_MIGRATOR_USER\" POSTGRES_PASSWORD=\"$$POSTGRES_MIGRATOR_PASSWORD\"
      python manage.py ensure_domains &&
  env POSTGRES_USER=\"$$POSTGRES_MIGRATOR_USER\" POSTGRES_PASSWORD=\"$$POSTGRES_MIGRATOR_PASSWORD\"
      python manage.py ensure_app_role &&
  exec uvicorn clinomic.asgi:application --host 0.0.0.0 --port 8000 --workers 4
  "
```

(`$$VAR` is compose's escape for `$VAR` — the literal `$` reaches
the shell inside the container so `env` substitutes from the
container's own env.)

Commit and deploy via the normal pipeline.

### 6. Remove the redundant deploy-pipeline migrate step

`.github/workflows/production-deploy.yml` currently runs
`docker exec backend python manage.py migrate_schemas` after
compose recreate. Once step 5 lands, the compose command handles
migrations under the migrator identity, so the deploy-pipeline
migrate is both redundant and would fail (backend container is
now running as the app user, which can't create schemas).

Delete the `=== APPLYING DJANGO MIGRATIONS ===` block entirely.
Rollback on migration failure now comes from the
`=== HEALTH CHECK ===` block — if migrations fail, the container
exits, healthcheck returns non-200, rollback runs.

## Rollback

If anything goes wrong, point `POSTGRES_USER` / `POSTGRES_PASSWORD`
back at the migrator credentials in `.env` and
`docker compose up -d --force-recreate backend`. The `clinomic_app`
role stays around, just unused. You lose nothing by trying the
cutover and reverting.

## What stays the same

- PgBouncer config — the app user authenticates through PgBouncer
  exactly like the migrator does. No auth_file change needed
  beyond adding the new user/hash pair to `userlist.txt`.
- Tests — CI still uses the superuser postgres role against the
  test database. `ensure_app_role` is a no-op when
  `POSTGRES_APP_USER` isn't set.
- Existing migrations — the migrator runs them. Nothing changes.

## Notes

- `ensure_app_role` always resets the app user's password from env.
  Rotating the password is a one-env-var change + container
  recreate. You don't have to touch Postgres directly.
- The `post_schema_sync` signal means onboarding flows that create
  new tenants (via `Organization.objects.create`) will grant the
  app user access automatically. No manual step for platform admins.
- If the post_schema_sync signal fails, the tenant create still
  succeeds — the failure is logged and the next deploy's
  `ensure_app_role` pass backfills the grants.

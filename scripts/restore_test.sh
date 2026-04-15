#!/usr/bin/env bash
#
# Database restore drill — restores the latest S3 backup into a scratch
# database on the same Postgres container and tears it down afterward.
#
# Usage (from the prod VM, in /opt/clinomic-b12-platform):
#     bash scripts/restore_test.sh
#
# See docs/RESTORE_TEST.md for context and troubleshooting.
#
# Safety:
#   - Never touches the live `clinomic` database
#   - Scratch DB is `clinomic_restore_test`, dropped on exit (trap)
#   - Read-only on S3 (no delete, no overwrite)

set -euo pipefail

SCRATCH_DB="clinomic_restore_test"
TMP_GZ="/tmp/clinomic_restore_test.dump.gz"
TMP_DUMP="/tmp/clinomic_restore_test.dump"
COMPOSE="docker compose -f docker-compose.prod.yml"

# Source .env to get S3 creds + DB password. Allow .env to not be at cwd if
# this script is being run from elsewhere; fall back to the canonical path.
if [[ -f .env ]]; then
    # shellcheck disable=SC1091
    set -a; source .env; set +a
elif [[ -f /opt/clinomic-b12-platform/.env ]]; then
    # shellcheck disable=SC1091
    set -a; source /opt/clinomic-b12-platform/.env; set +a
else
    echo "ERROR: .env not found in cwd or /opt/clinomic-b12-platform/" >&2
    exit 1
fi

: "${BACKUP_S3_BUCKET:?BACKUP_S3_BUCKET must be set in .env}"
: "${AWS_BACKUP_ACCESS_KEY_ID:?AWS_BACKUP_ACCESS_KEY_ID must be set}"
: "${AWS_BACKUP_SECRET_ACCESS_KEY:?AWS_BACKUP_SECRET_ACCESS_KEY must be set}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"
: "${POSTGRES_USER:=postgres}"

PREFIX="${BACKUP_S3_PREFIX:-db-backups/}"

cleanup() {
    local rc=$?
    echo "Cleaning up scratch DB ..."
    $COMPOSE exec -T db psql -U "$POSTGRES_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS $SCRATCH_DB;" >/dev/null 2>&1 || true
    rm -f "$TMP_GZ" "$TMP_DUMP"
    if [[ $rc -eq 0 ]]; then
        echo "Restore drill PASSED."
    else
        echo "Restore drill FAILED (exit $rc)." >&2
    fi
    exit $rc
}
trap cleanup EXIT

echo "[1/6] Listing most recent backup in S3 ..."
LATEST=$(AWS_ACCESS_KEY_ID="$AWS_BACKUP_ACCESS_KEY_ID" \
         AWS_SECRET_ACCESS_KEY="$AWS_BACKUP_SECRET_ACCESS_KEY" \
         aws s3 ls "s3://${BACKUP_S3_BUCKET}/${PREFIX}" \
         | sort -k1,2 \
         | tail -1 \
         | awk '{print $4}')
if [[ -z "$LATEST" ]]; then
    echo "ERROR: no backups found at s3://${BACKUP_S3_BUCKET}/${PREFIX}" >&2
    echo "       Trigger a backup first:" >&2
    echo "       $COMPOSE exec celery_worker celery -A clinomic call core.backup_database" >&2
    exit 2
fi
echo "      s3://${BACKUP_S3_BUCKET}/${PREFIX}${LATEST}"

echo "[2/6] Downloading to $TMP_GZ ..."
AWS_ACCESS_KEY_ID="$AWS_BACKUP_ACCESS_KEY_ID" \
AWS_SECRET_ACCESS_KEY="$AWS_BACKUP_SECRET_ACCESS_KEY" \
    aws s3 cp "s3://${BACKUP_S3_BUCKET}/${PREFIX}${LATEST}" "$TMP_GZ" --only-show-errors
SIZE=$(du -h "$TMP_GZ" | awk '{print $1}')
echo "      OK ($SIZE)"

echo "[3/6] Gunzipping ..."
gunzip -c "$TMP_GZ" > "$TMP_DUMP"
DUMP_SIZE=$(du -h "$TMP_DUMP" | awk '{print $1}')
echo "      OK ($DUMP_SIZE uncompressed)"

echo "[4/6] Creating scratch database $SCRATCH_DB ..."
# Ensure the scratch DB is clean. -T disables TTY allocation so this
# works under CI/non-interactive shells too.
$COMPOSE exec -T db psql -U "$POSTGRES_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS $SCRATCH_DB;" >/dev/null
$COMPOSE exec -T db psql -U "$POSTGRES_USER" -d postgres \
    -c "CREATE DATABASE $SCRATCH_DB;"

echo "[5/6] pg_restore into scratch ..."
# Stream the dump into the container via stdin so we don't have to copy
# files into the volume.
$COMPOSE exec -T db pg_restore \
    --username="$POSTGRES_USER" \
    --dbname="$SCRATCH_DB" \
    --no-owner --no-acl \
    --exit-on-error < "$TMP_DUMP"
echo "      OK"

echo "[6/6] Sanity queries ..."
# Queries against the scratch DB — tolerate schema shape differences by
# joining information_schema only for table existence.
# The screenings table lives in tenant schemas, not public, so iterate.
$COMPOSE exec -T db psql -U "$POSTGRES_USER" -d "$SCRATCH_DB" -c "
DO \$\$
DECLARE
    s       record;
    scr_count  bigint := 0;
    usr_count  bigint := 0;
    org_count  bigint := 0;
    latest_ts  text;
BEGIN
    -- Organizations live in public
    SELECT count(*) INTO org_count FROM public.core_organization;
    SELECT count(*) INTO usr_count FROM public.core_user;

    -- Aggregate screenings across all tenant schemas
    FOR s IN SELECT nspname FROM pg_namespace
             WHERE nspname NOT IN ('public','information_schema','pg_catalog','pg_toast')
               AND nspname NOT LIKE 'pg_%'
    LOOP
        EXECUTE format(
            'SELECT count(*) FROM %I.screening_screening',
            s.nspname
        ) INTO STRICT scr_count;
        RAISE NOTICE '      tenant % screenings: %', s.nspname, scr_count;
    END LOOP;

    RAISE NOTICE '      users (public):         %', usr_count;
    RAISE NOTICE '      organizations (public): %', org_count;
END \$\$;
"

# cleanup trap fires on EXIT

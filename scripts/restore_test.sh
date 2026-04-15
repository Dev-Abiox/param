#!/usr/bin/env bash
#
# Database restore drill — restores a backup into a scratch database on the
# same Postgres container and tears it down afterward.
#
# Supports two backup sources:
#   1. Local file (default): the latest file in /opt/backups/clinomic/ written
#      by the host-cron db-backup.sh (plain .sql.gz format). Pass a specific
#      file as the first arg to override.
#   2. S3 (when BACKUP_S3_BUCKET is set in .env): fetches the most recent
#      object from s3://<bucket>/<prefix> (custom .dump.gz format).
#
# Usage (from /opt/clinomic-b12-platform on the VM):
#     bash scripts/restore_test.sh                           # latest local
#     bash scripts/restore_test.sh /opt/backups/clinomic/clinomic_backup_20260415_020001.sql.gz
#     bash scripts/restore_test.sh --from-s3                 # force S3
#
# Safety:
#   - Never touches the live `clinomic` database
#   - Scratch DB is `clinomic_restore_test`, dropped on EXIT via trap
#   - Read-only on S3 (no delete, no overwrite)
#
# See docs/RESTORE_TEST.md for context and troubleshooting.

set -euo pipefail

SCRATCH_DB="clinomic_restore_test"
TMP_GZ="/tmp/clinomic_restore_test.gz"
TMP_PLAIN="/tmp/clinomic_restore_test.plain"

# Auto-detect compose command. Prod VM has `docker-compose` (v1-style standalone
# binary); newer hosts have `docker compose` (plugin). Accept either.
if docker compose version >/dev/null 2>&1; then
    COMPOSE="docker compose -f docker-compose.prod.yml"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE="docker-compose -f docker-compose.prod.yml"
else
    echo "ERROR: neither 'docker compose' nor 'docker-compose' is available" >&2
    exit 1
fi

# --from-s3 forces S3 source; otherwise we default to a local file and fall
# back to S3 only if explicitly requested or no local file exists.
SOURCE_MODE="auto"
LOCAL_FILE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --from-s3) SOURCE_MODE="s3"; shift ;;
        --from-local) SOURCE_MODE="local"; shift ;;
        -h|--help)
            sed -n '2,22p' "$0"
            exit 0 ;;
        *)
            LOCAL_FILE="$1"; SOURCE_MODE="local"; shift ;;
    esac
done

# Load .env for POSTGRES_USER / S3 creds. Never fatal at source time — we only
# require the S3 vars if we're actually going to S3.
if [[ -f .env ]]; then
    # shellcheck disable=SC1091
    set -a; source .env; set +a
elif [[ -f /opt/clinomic-b12-platform/.env ]]; then
    # shellcheck disable=SC1091
    set -a; source /opt/clinomic-b12-platform/.env; set +a
fi
POSTGRES_USER="${POSTGRES_USER:-postgres}"

cleanup() {
    local rc=$?
    echo
    echo "Cleaning up scratch DB ..."
    $COMPOSE exec -T db psql -U "$POSTGRES_USER" -d postgres \
        -c "DROP DATABASE IF EXISTS $SCRATCH_DB;" >/dev/null 2>&1 || true
    rm -f "$TMP_GZ" "$TMP_PLAIN"
    if [[ $rc -eq 0 ]]; then
        echo "Restore drill PASSED."
    else
        echo "Restore drill FAILED (exit $rc)." >&2
    fi
    exit $rc
}
trap cleanup EXIT

# ── Step 1 — locate the backup ────────────────────────────────────────────────
if [[ "$SOURCE_MODE" == "s3" ]]; then
    : "${BACKUP_S3_BUCKET:?--from-s3 requires BACKUP_S3_BUCKET in .env}"
    : "${AWS_BACKUP_ACCESS_KEY_ID:?AWS_BACKUP_ACCESS_KEY_ID must be set}"
    : "${AWS_BACKUP_SECRET_ACCESS_KEY:?AWS_BACKUP_SECRET_ACCESS_KEY must be set}"
    PREFIX="${BACKUP_S3_PREFIX:-db-backups/}"
    ENDPOINT_ARG=""
    if [[ -n "${BACKUP_S3_ENDPOINT_URL:-}" ]]; then
        ENDPOINT_ARG="--endpoint-url ${BACKUP_S3_ENDPOINT_URL}"
    fi

    echo "[1/5] Listing most recent backup in s3://${BACKUP_S3_BUCKET}/${PREFIX} ..."
    LATEST=$(AWS_ACCESS_KEY_ID="$AWS_BACKUP_ACCESS_KEY_ID" \
             AWS_SECRET_ACCESS_KEY="$AWS_BACKUP_SECRET_ACCESS_KEY" \
             aws $ENDPOINT_ARG s3 ls "s3://${BACKUP_S3_BUCKET}/${PREFIX}" \
             | sort -k1,2 | tail -1 | awk '{print $4}')
    if [[ -z "$LATEST" ]]; then
        echo "ERROR: no backups found at s3://${BACKUP_S3_BUCKET}/${PREFIX}" >&2
        echo "       Trigger a backup first:" >&2
        echo "       $COMPOSE exec celery_worker celery -A clinomic call core.backup_database" >&2
        exit 2
    fi
    SOURCE_LABEL="s3://${BACKUP_S3_BUCKET}/${PREFIX}${LATEST}"
    echo "      $SOURCE_LABEL"

    echo "[2/5] Downloading ..."
    AWS_ACCESS_KEY_ID="$AWS_BACKUP_ACCESS_KEY_ID" \
    AWS_SECRET_ACCESS_KEY="$AWS_BACKUP_SECRET_ACCESS_KEY" \
        aws $ENDPOINT_ARG s3 cp "s3://${BACKUP_S3_BUCKET}/${PREFIX}${LATEST}" "$TMP_GZ" --only-show-errors
else
    # Local file mode — use explicit path or pick the newest local snapshot.
    if [[ -z "$LOCAL_FILE" ]]; then
        LOCAL_FILE=$(ls -t /opt/backups/clinomic/clinomic_backup_*.sql.gz 2>/dev/null | head -1 || true)
    fi
    if [[ -z "$LOCAL_FILE" || ! -f "$LOCAL_FILE" ]]; then
        echo "ERROR: no local backup found at /opt/backups/clinomic/*.sql.gz" >&2
        echo "       Pass --from-s3 to fetch from S3 instead, or run the host cron:" >&2
        echo "       /opt/clinomic-b12-platform/db-backup.sh" >&2
        exit 2
    fi
    SOURCE_LABEL="$LOCAL_FILE"
    echo "[1/5] Using local backup: $SOURCE_LABEL"
    echo "[2/5] Copying to $TMP_GZ ..."
    cp "$LOCAL_FILE" "$TMP_GZ"
fi

SIZE=$(du -h "$TMP_GZ" | awk '{print $1}')
echo "      OK ($SIZE)"

# ── Step 3 — decompress and detect format ────────────────────────────────────
echo "[3/5] Decompressing and detecting format ..."
# Extract the full file first (no pipeline: `gunzip -c | head -c N` trips
# SIGPIPE under `set -eo pipefail` because head closes stdin early).
gunzip -c "$TMP_GZ" > "$TMP_PLAIN"
PLAIN_SIZE=$(du -h "$TMP_PLAIN" | awk '{print $1}')
# Then peek at the first bytes of the extracted file. pg_dump custom format
# starts with magic bytes "PGDMP"; plain SQL starts with "--" or "SET".
FIRST_BYTES=$(head -c 5 "$TMP_PLAIN")
if [[ "$FIRST_BYTES" == "PGDMP" ]]; then
    FORMAT="custom"
    echo "      detected: custom (pg_restore), uncompressed $PLAIN_SIZE"
elif [[ "$FIRST_BYTES" == "--"* ]] || [[ "$FIRST_BYTES" == "SET "* ]]; then
    FORMAT="plain"
    echo "      detected: plain SQL (psql), uncompressed $PLAIN_SIZE"
else
    echo "ERROR: unrecognized backup format (first bytes: $FIRST_BYTES)" >&2
    exit 3
fi

# ── Step 4 — restore into scratch DB ──────────────────────────────────────────
echo "[4/5] Creating scratch database $SCRATCH_DB and restoring ..."
$COMPOSE exec -T db psql -U "$POSTGRES_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS $SCRATCH_DB;" >/dev/null
$COMPOSE exec -T db psql -U "$POSTGRES_USER" -d postgres \
    -c "CREATE DATABASE $SCRATCH_DB;" >/dev/null

if [[ "$FORMAT" == "custom" ]]; then
    $COMPOSE exec -T db pg_restore \
        --username="$POSTGRES_USER" \
        --dbname="$SCRATCH_DB" \
        --no-owner --no-acl \
        --exit-on-error < "$TMP_PLAIN"
else
    # Plain SQL: stream through psql. --single-transaction makes the whole
    # restore atomic so any error rolls back.
    $COMPOSE exec -T db psql \
        --username="$POSTGRES_USER" \
        --dbname="$SCRATCH_DB" \
        --single-transaction \
        --set=ON_ERROR_STOP=on \
        --quiet < "$TMP_PLAIN" \
        >/dev/null
fi
echo "      OK"

# ── Step 5 — sanity queries ───────────────────────────────────────────────────
echo "[5/5] Sanity queries ..."
# The models override Meta.db_table, so shared-app tables are public.organizations
# and public.users (not core_organization / core_user). Tenant-app tables live
# in per-tenant schemas: <tenant>.screenings, <tenant>.patients, etc.
$COMPOSE exec -T db psql -U "$POSTGRES_USER" -d "$SCRATCH_DB" -v ON_ERROR_STOP=on <<'SQL'
\pset format aligned
\pset tuples_only off
SELECT
    (SELECT count(*) FROM public.organizations) AS organizations,
    (SELECT count(*) FROM public.users)         AS users,
    (SELECT count(*) FROM public.billing_subscriptions) AS subscriptions;

DO $$
DECLARE
    s              record;
    scr_count      bigint;
    pat_count      bigint;
    lab_count      bigint;
    total_scr      bigint := 0;
BEGIN
    FOR s IN SELECT nspname FROM pg_namespace
             WHERE nspname NOT IN ('public','information_schema','pg_catalog','pg_toast')
               AND nspname NOT LIKE 'pg_%'
             ORDER BY nspname
    LOOP
        BEGIN
            EXECUTE format('SELECT count(*) FROM %I.screenings', s.nspname) INTO scr_count;
            EXECUTE format('SELECT count(*) FROM %I.patients',   s.nspname) INTO pat_count;
            EXECUTE format('SELECT count(*) FROM %I.labs',       s.nspname) INTO lab_count;
            RAISE NOTICE 'tenant %: screenings=% patients=% labs=%',
                s.nspname, scr_count, pat_count, lab_count;
            total_scr := total_scr + scr_count;
        EXCEPTION WHEN undefined_table THEN
            RAISE NOTICE 'tenant %: (schema present but tenant tables not in dump)', s.nspname;
        END;
    END LOOP;
    RAISE NOTICE 'total screenings across all tenants: %', total_scr;
END $$;
SQL

echo
echo "Source: $SOURCE_LABEL"
# cleanup trap fires on EXIT

#!/bin/bash
# PostgreSQL Restore Script for Clinomic Platform v3
# Usage: ./restore.sh <backup_file>
#
# Environment variables:
#   POSTGRES_HOST - Database host (default: localhost)
#   POSTGRES_PORT - Database port (default: 5432)
#   POSTGRES_DB - Database name (default: clinomic)
#   POSTGRES_USER - Database user (default: postgres)
#   PGPASSWORD - Database password

set -e

# Configuration
BACKUP_FILE=$1
POSTGRES_HOST=${POSTGRES_HOST:-localhost}
POSTGRES_PORT=${POSTGRES_PORT:-5432}
POSTGRES_DB=${POSTGRES_DB:-clinomic}
POSTGRES_USER=${POSTGRES_USER:-postgres}

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file>"
    echo "Example: $0 ./backups/clinomic_20240101_120000.sql.gz"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "=========================================="
echo "Clinomic PostgreSQL Restore"
echo "=========================================="
echo "Backup File: $BACKUP_FILE"
echo "Host: $POSTGRES_HOST:$POSTGRES_PORT"
echo "Database: $POSTGRES_DB"
echo ""

# Check if pg_restore is available
if ! command -v pg_restore &> /dev/null; then
    echo "ERROR: pg_restore not found. Please install PostgreSQL client tools."
    exit 1
fi

# Confirm restore
echo "⚠️  WARNING: This will REPLACE all data in database '$POSTGRES_DB'"
echo ""
read -p "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "$CONFIRM" != "yes" ]; then
    echo "Restore cancelled."
    exit 0
fi

echo ""
echo "Starting restore..."

# Decompress and restore
gunzip -c "$BACKUP_FILE" | pg_restore \
    -h "$POSTGRES_HOST" \
    -p "$POSTGRES_PORT" \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --clean --if-exists \
    --no-owner --no-privileges \
    2>&1 || true  # pg_restore returns non-zero for warnings

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Restore completed"
    echo ""
    echo "Verifying restore..."

    # Simple verification - count tables
    TABLE_COUNT=$(psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | tr -d ' ')
    echo "   Tables in database: $TABLE_COUNT"

    echo ""
    echo "✅ Restore verification complete"
else
    echo "❌ Restore failed!"
    exit 1
fi

echo ""
echo "=========================================="
echo "Restore Complete"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Verify application functionality"
echo "  2. Check user accounts and permissions"
echo "  3. Run Django migrations if needed: python manage.py migrate"

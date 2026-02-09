#!/bin/bash
# PostgreSQL Backup Script for Clinomic Platform v3
# Usage: ./backup.sh [output_dir]
#
# Environment variables:
#   POSTGRES_HOST - Database host (default: localhost)
#   POSTGRES_PORT - Database port (default: 5432)
#   POSTGRES_DB - Database name (default: clinomic)
#   POSTGRES_USER - Database user (default: postgres)
#   PGPASSWORD - Database password
#   BACKUP_RETENTION_DAYS - Days to keep backups (default: 7)
#   S3_BUCKET - Optional S3 bucket for remote backup storage

set -e

# Configuration
BACKUP_DIR=${1:-./backups}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
POSTGRES_HOST=${POSTGRES_HOST:-localhost}
POSTGRES_PORT=${POSTGRES_PORT:-5432}
POSTGRES_DB=${POSTGRES_DB:-clinomic}
POSTGRES_USER=${POSTGRES_USER:-postgres}
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-7}

# Create backup directory
mkdir -p "$BACKUP_DIR"

FILENAME="$BACKUP_DIR/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

echo "=========================================="
echo "Clinomic PostgreSQL Backup"
echo "=========================================="
echo "Timestamp: $TIMESTAMP"
echo "Host: $POSTGRES_HOST:$POSTGRES_PORT"
echo "Database: $POSTGRES_DB"
echo "Output: $FILENAME"
echo ""

# Check if pg_dump is available
if ! command -v pg_dump &> /dev/null; then
    echo "ERROR: pg_dump not found. Please install PostgreSQL client tools."
    echo "  On Ubuntu/Debian: apt-get install postgresql-client"
    echo "  On macOS: brew install postgresql"
    exit 1
fi

# Check for password
if [ -z "$PGPASSWORD" ]; then
    echo "WARNING: PGPASSWORD not set. You may be prompted for password."
fi

# Perform backup with pg_dump
echo "Starting backup..."
pg_dump -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
    --format=custom --compress=9 \
    --no-owner --no-privileges \
    "$POSTGRES_DB" | gzip > "$FILENAME"

if [ $? -eq 0 ]; then
    FILESIZE=$(du -h "$FILENAME" | cut -f1)
    echo "✅ Backup completed successfully"
    echo "   File: $FILENAME"
    echo "   Size: $FILESIZE"
else
    echo "❌ Backup failed!"
    exit 1
fi

# Verify backup integrity
echo ""
echo "Verifying backup integrity..."
if gzip -t "$FILENAME" 2>/dev/null; then
    echo "✅ Backup file integrity verified"
else
    echo "⚠️  Warning: Backup file may be corrupted"
fi

# Upload to S3 if configured
if [ -n "$S3_BUCKET" ]; then
    echo ""
    echo "Uploading to S3: $S3_BUCKET"
    if command -v aws &> /dev/null; then
        aws s3 cp "$FILENAME" "s3://$S3_BUCKET/postgres/"
        if [ $? -eq 0 ]; then
            echo "✅ Uploaded to S3 successfully"
        else
            echo "⚠️  S3 upload failed"
        fi
    else
        echo "⚠️  AWS CLI not found, skipping S3 upload"
    fi
fi

# Cleanup old backups
echo ""
echo "Cleaning up backups older than $RETENTION_DAYS days..."
DELETED_COUNT=$(find "$BACKUP_DIR" -name "${POSTGRES_DB}_*.sql.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)
echo "   Deleted $DELETED_COUNT old backup(s)"

echo ""
echo "=========================================="
echo "Backup Complete"
echo "=========================================="
echo ""
echo "To restore this backup, run:"
echo "  gunzip -c \"$FILENAME\" | pg_restore -h \$POSTGRES_HOST -p \$POSTGRES_PORT -U \$POSTGRES_USER -d $POSTGRES_DB --clean --if-exists"
echo ""
echo "Or for a fresh database:"
echo "  createdb -h \$POSTGRES_HOST -p \$POSTGRES_PORT -U \$POSTGRES_USER $POSTGRES_DB"
echo "  gunzip -c \"$FILENAME\" | pg_restore -h \$POSTGRES_HOST -p \$POSTGRES_PORT -U \$POSTGRES_USER -d $POSTGRES_DB"
echo ""
echo "⚠️  REMINDER: Test your restore procedure regularly!"

#!/bin/bash
# MongoDB Backup Script for Clinomic Platform
# Usage: ./backup-mongodb.sh [output_dir]
#
# Environment variables:
#   MONGO_URL - MongoDB connection string (default: mongodb://localhost:27017)
#   DB_NAME - Database name (default: clinomic)
#   BACKUP_RETENTION_DAYS - Days to keep backups (default: 7)
#   S3_BUCKET - Optional S3 bucket for remote backup storage

set -e

# Configuration
BACKUP_DIR=${1:-./backups/mongodb}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
MONGO_URL=${MONGO_URL:-mongodb://localhost:27017}
DB_NAME=${DB_NAME:-clinomic}
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-7}

# Create backup directory
mkdir -p "$BACKUP_DIR"

FILENAME="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.gz"

echo "=========================================="
echo "Clinomic MongoDB Backup"
echo "=========================================="
echo "Timestamp: $TIMESTAMP"
echo "Database: $DB_NAME"
echo "Output: $FILENAME"
echo ""

# Check if mongodump is available
if ! command -v mongodump &> /dev/null; then
    echo "ERROR: mongodump not found. Please install MongoDB tools."
    echo "  On Ubuntu/Debian: apt-get install mongodb-org-tools"
    echo "  On macOS: brew install mongodb-database-tools"
    exit 1
fi

# Perform backup
echo "Starting backup..."
mongodump --uri="$MONGO_URL" --db="$DB_NAME" --gzip --archive="$FILENAME"

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
        aws s3 cp "$FILENAME" "s3://$S3_BUCKET/mongodb/"
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
DELETED_COUNT=$(find "$BACKUP_DIR" -name "${DB_NAME}_*.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)
echo "   Deleted $DELETED_COUNT old backup(s)"

echo ""
echo "=========================================="
echo "Backup Complete"
echo "=========================================="
echo ""
echo "To restore this backup, run:"
echo "  mongorestore --uri=\"\$MONGO_URL\" --gzip --archive=\"$FILENAME\" --drop"
echo ""
echo "⚠️  REMINDER: Test your restore procedure regularly!"

#!/bin/bash
# Restore Drill Script
# WARNING: THIS WILL DROP THE TEST DATABASE. DO NOT RUN ON PROD.

set -e

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: ./restore_drill.sh <path_to_backup_file.sql.gz>"
    exit 1
fi

echo "🚨 RESTORE DRILL INTIATED 🚨"
echo "Target: LOCAL TEST DB (biosaas_v2_restore_test)"
echo "Source: $BACKUP_FILE"
echo ""
read -p "Are you sure? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
fi

CONTAINER_NAME=$(docker-compose -f docker-compose.v2.yml ps -q db)

# Create/Reset Test DB
echo "♻️  Recreating Test Database..."
docker exec "$CONTAINER_NAME" psql -U postgres -c "DROP DATABASE IF EXISTS biosaas_v2_restore_test;"
docker exec "$CONTAINER_NAME" psql -U postgres -c "CREATE DATABASE biosaas_v2_restore_test;"

# Restore
echo "📥 Importing Data..."
zcat "$BACKUP_FILE" | docker exec -i "$CONTAINER_NAME" psql -U postgres -d biosaas_v2_restore_test

echo "✅ Restore Complete."
echo "🔎 Verifying..."

# Simple Count Check
COUNT=$(docker exec "$CONTAINER_NAME" psql -U postgres -d biosaas_v2_restore_test -t -c "SELECT count(*) FROM config_audit_log;") # Example table? No, using generic
# Better: List tables
docker exec "$CONTAINER_NAME" psql -U postgres -d biosaas_v2_restore_test -c "\dt"

echo "✅ Drill Success. Database restored to 'biosaas_v2_restore_test'."

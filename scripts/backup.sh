#!/bin/bash
# Backup Script for BioSaaS V2
# Usage: ./backup.sh [output_dir]

set -e

BACKUP_DIR=${1:-./backups}
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="$BACKUP_DIR/biosaas_v2_$TIMESTAMP.sql.gz"

echo "POSTGRES_USER: ${POSTGRES_USER}"
echo "Starting Backup to $FILENAME..."

# Dump via Docker container
# Assumes container name 'db' from docker-compose or based on folder name
# In production, use exact container name
CONTAINER_NAME=$(docker-compose -f docker-compose.v2.yml ps -q db)

if [ -z "$CONTAINER_NAME" ]; then
    echo "Error: DB Container not found. Is docker-compose running?"
    exit 1
fi

docker exec -t "$CONTAINER_NAME" pg_dump -U postgres biosaas_v2 | gzip > "$FILENAME"

echo "✅ Backup Complete: $FILENAME"
echo "⚠️  REMINDER: Verify this backup by running ./restore_drill.sh"

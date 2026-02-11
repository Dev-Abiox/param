#!/bin/bash

# Daily Database Backup Script for Clinomic B12 Platform
# This script creates a PostgreSQL backup and stores it with timestamp

set -e  # Exit on any error

# Configuration
BACKUP_DIR="/opt/backups/clinomic"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="clinomic_backup_$DATE.sql"
LOG_FILE="/var/log/clinomic_backup.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a $LOG_FILE
}

success() {
    echo -e "${GREEN}$1${NC}" | tee -a $LOG_FILE
}

warning() {
    echo -e "${YELLOW}$1${NC}" | tee -a $LOG_FILE
}

error() {
    echo -e "${RED}$1${NC}" | tee -a $LOG_FILE
}

# Create backup directory if it doesn't exist
mkdir -p $BACKUP_DIR

log "Starting database backup..."

# Create backup
if docker exec clinomic-db-1 pg_dump -U postgres clinomic > "$BACKUP_DIR/$BACKUP_FILE" 2>>$LOG_FILE; then
    success "Database backup created successfully: $BACKUP_DIR/$BACKUP_FILE"
    
    # Compress the backup
    gzip "$BACKUP_DIR/$BACKUP_FILE"
    success "Backup compressed: $BACKUP_DIR/${BACKUP_FILE}.gz"
    
    # Remove backups older than 7 days
    find $BACKUP_DIR -name "clinomic_backup_*.sql.gz" -mtime +7 -delete
    log "Old backups cleaned up (older than 7 days)"
    
    # Report backup size
    BACKUP_SIZE=$(du -h "$BACKUP_DIR/${BACKUP_FILE}.gz" | cut -f1)
    success "Backup size: $BACKUP_SIZE"
    
else
    error "Database backup failed"
    exit 1
fi

log "Database backup completed successfully"
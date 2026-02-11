#!/bin/bash

# Setup Daily Database Backup Cron Job
# Adds a cron job to run db-backup.sh daily at 2 AM

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/db-backup.sh"
CRON_JOB="0 2 * * * $BACKUP_SCRIPT >> /var/log/clinomic_backup.log 2>&1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

success() {
    echo -e "${GREEN}$1${NC}"
}

warning() {
    echo -e "${YELLOW}$1${NC}"
}

error() {
    echo -e "${RED}$1${NC}"
}

# Make backup script executable
chmod +x "$BACKUP_SCRIPT"
success "Made backup script executable"

# Add cron job
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
success "Added daily backup cron job (runs at 2 AM)"

# Verify cron job was added
if crontab -l | grep -q "db-backup.sh"; then
    success "Cron job verified successfully"
    echo "Current cron jobs:"
    crontab -l | grep "db-backup.sh" || true
else
    error "Failed to add cron job"
    exit 1
fi

success "Daily database backup setup completed!"
echo ""
echo "Backup details:"
echo "- Script: $BACKUP_SCRIPT"
echo "- Schedule: Daily at 2:00 AM"
echo "- Backup location: /opt/backups/clinomic/"
echo "- Log file: /var/log/clinomic_backup.log"
echo "- Retention: 7 days"
#!/bin/bash
# ============================================================================
# CLINOMIC MONITORING SETUP SCRIPT
# ============================================================================
# Sets up monitoring services for the Clinomic application
# Installs and configures health checks, logging, and alerting
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}==========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Configuration
DEPLOY_USER="deploy"
DEPLOY_PATH="/opt/clinomic"
MONITORING_PATH="/opt/clinomic-monitoring"
LOG_PATH="/var/log/clinomic"
SERVICE_USER="clinomic-monitor"

print_header "CLINOMIC MONITORING SETUP"

echo "This script will:"
echo "1. Create monitoring directories"
echo "2. Set up health check scripts"
echo "3. Configure log rotation"
echo "4. Create systemd services for monitoring"
echo ""

read -p "Continue with monitoring setup? (yes/no): " confirm
if [[ $confirm != "yes" ]]; then
    echo "Monitoring setup cancelled"
    exit 0
fi

# Create monitoring directories
print_header "CREATING MONITORING DIRECTORIES"
mkdir -p $MONITORING_PATH
mkdir -p $LOG_PATH
mkdir -p /etc/clinomic-monitoring

# Create log files with proper permissions
touch $LOG_PATH/health-check.log
touch $LOG_PATH/alerts.log
touch $LOG_PATH/dashboard.log
chown -R $DEPLOY_USER:$DEPLOY_USER $LOG_PATH
chmod -R 644 $LOG_PATH/*.log
print_success "Monitoring directories created"

# Copy health check script to monitoring directory
cat > $MONITORING_PATH/health-check.sh << 'EOF'
#!/bin/bash
# Health check script for Clinomic application

HEALTH_URL="http://localhost:8000/api/health/live"
READY_URL="http://localhost:8000/api/health/ready"
BACKEND_URL="http://localhost:8000"
TIMEOUT=30
LOG_FILE="/var/log/clinomic/health-check.log"

log_check() {
    echo "$(date -Iseconds) | $1" >> $LOG_FILE
}

# Check live health
if curl -sf --connect-timeout 5 --max-time $TIMEOUT "$HEALTH_URL" > /dev/null 2>&1; then
    log_check "HEALTH_CHECK OK | Live endpoint responding"
    exit 0
else
    log_check "HEALTH_CHECK FAILED | Live endpoint not responding"
    exit 1
fi
EOF

chmod +x $MONITORING_PATH/health-check.sh
chown $DEPLOY_USER:$DEPLOY_USER $MONITORING_PATH/health-check.sh
print_success "Health check script created"

# Create log rotation configuration
cat > /etc/logrotate.d/clinomic << 'EOF'
/var/log/clinomic/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 deploy deploy
    postrotate
        # Signal services to reopen log files if needed
    endscript
}
EOF

print_success "Log rotation configured"

# Create systemd service for health monitoring
cat > /etc/systemd/system/clinomic-health-monitor.service << 'EOF'
[Unit]
Description=Clinomic Health Monitor Service
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=deploy
ExecStart=/bin/bash -c '/opt/clinomic-monitoring/health-check.sh'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# Create systemd timer for periodic health checks
cat > /etc/systemd/system/clinomic-health-monitor.timer << 'EOF'
[Unit]
Description=Run Clinomic health checks every minute
Requires=clinomic-health-monitor.service

[Timer]
OnBootSec=1min
OnUnitActiveSec=1min

[Install]
WantedBy=timers.target
EOF

print_success "Systemd services created"

# Create monitoring dashboard service
cat > /etc/systemd/system/clinomic-dashboard.service << 'EOF'
[Unit]
Description=Clinomic Monitoring Dashboard
After=docker.service
Requires=docker.service

[Service]
Type=forking
User=deploy
ExecStart=/opt/clinomic-monitoring/dashboard.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# Create alerting script
cat > $MONITORING_PATH/alert-handler.sh << 'EOF'
#!/bin/bash
# Alert handling script for Clinomic application

ALERT_LOG="/var/log/clinomic/alerts.log"
HEALTH_LOG="/var/log/clinomic/health-check.log"

# Function to send alerts (placeholder - customize for your needs)
send_alert() {
    local message=$1
    local severity=${2:-"INFO"}
    
    echo "$(date -Iseconds) [$severity] $message" >> $ALERT_LOG
    
    # Here you could integrate with external systems like:
    # - Email notifications
    # - Slack/webhook integrations
    # - PagerDuty, etc.
    
    # For now, just log the alert
    echo "ALERT SENT: $message (Severity: $severity)"
}

# Check for recent health check failures
check_for_failures() {
    local recent_failures=$(tail -20 $HEALTH_LOG | grep -c "FAILED\|ERROR")
    
    if [[ $recent_failures -gt 0 ]]; then
        send_alert "Health check failures detected: $recent_failures in last 20 checks" "WARNING"
    fi
}

# Check for service restarts
check_service_status() {
    local services=("db" "backend" "frontend" "nginx")
    
    for service in "${services[@]}"; do
        local container=$(docker ps --format '{{.Names}}' | grep -i "$service" | head -n1)
        
        if [[ -n "$container" ]]; then
            local status=$(docker ps --filter "name=$container" --format '{{.Status}}')
            
            if [[ ! $status =~ ^Up.* ]]; then
                send_alert "Service $container is not running: $status" "CRITICAL"
            fi
        else
            send_alert "Service $service container not found" "CRITICAL"
        fi
    done
}

# Main alert check
main() {
    check_for_failures
    check_service_status
}

main
EOF

chmod +x $MONITORING_PATH/alert-handler.sh
chown $DEPLOY_USER:$DEPLOY_USER $MONITORING_PATH/alert-handler.sh
print_success "Alert handler created"

# Create a monitoring report script
cat > $MONITORING_PATH/generate-report.sh << 'EOF'
#!/bin/bash
# Generate monitoring report for Clinomic application

REPORT_DIR="/opt/clinomic-monitoring/reports"
mkdir -p $REPORT_DIR

DATE=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="$REPORT_DIR/clinomic_report_$DATE.txt"

# Get system info
echo "CLINOMIC APPLICATION REPORT" > $REPORT_FILE
echo "Generated on: $(date)" >> $REPORT_FILE
echo "=========================" >> $REPORT_FILE
echo "" >> $REPORT_FILE

# System resources
echo "SYSTEM RESOURCES" >> $REPORT_FILE
echo "----------------" >> $REPORT_FILE
echo "Memory:" >> $REPORT_FILE
free -h >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "Disk Usage:" >> $REPORT_FILE
df -h / >> $REPORT_FILE
echo "" >> $REPORT_FILE

# Service status
echo "SERVICE STATUS" >> $REPORT_FILE
echo "--------------" >> $REPORT_FILE
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" >> $REPORT_FILE
echo "" >> $REPORT_FILE

# Recent health checks
echo "RECENT HEALTH CHECKS" >> $REPORT_FILE
echo "--------------------" >> $REPORT_FILE
tail -20 /var/log/clinomic/health-check.log >> $REPORT_FILE
echo "" >> $REPORT_FILE

# Recent alerts
echo "RECENT ALERTS" >> $REPORT_FILE
echo "-------------" >> $REPORT_FILE
tail -10 /var/log/clinomic/alerts.log >> $REPORT_FILE
echo "" >> $REPORT_FILE

echo "Report generated: $REPORT_FILE"
EOF

chmod +x $MONITORING_PATH/generate-report.sh
chown $DEPLOY_USER:$DEPLOY_USER $MONITORING_PATH/generate-report.sh
print_success "Report generation script created"

# Enable and start monitoring services
print_header "ENABLING MONITORING SERVICES"

systemctl daemon-reload

# Enable the health check timer
systemctl enable clinomic-health-monitor.timer
systemctl start clinomic-health-monitor.timer

print_success "Health monitoring timer enabled and started"

# Create a cron job for running the alert handler periodically
cat > /etc/cron.d/clinomic-alerts << 'EOF'
# Run alert checks every 5 minutes
*/5 * * * * deploy /opt/clinomic-monitoring/alert-handler.sh >> /var/log/clinomic/dashboard.log 2>&1
EOF

print_success "Cron job for alert handling created"

# Create a startup script to ensure monitoring starts after reboot
cat > /opt/clinomic-monitoring/start-monitoring.sh << 'EOF'
#!/bin/bash
# Startup script for Clinomic monitoring

echo "$(date -Iseconds) - Starting Clinomic monitoring services" >> /var/log/clinomic/dashboard.log

# Wait a bit for Docker to be fully ready
sleep 10

# Ensure the main application is running
cd /opt/clinomic
docker-compose -f docker-compose.prod.yml up -d

# Start monitoring services
systemctl start clinomic-health-monitor.timer

echo "$(date -Iseconds) - Monitoring services started" >> /var/log/clinomic/dashboard.log
EOF

chmod +x /opt/clinomic-monitoring/start-monitoring.sh
chown $DEPLOY_USER:$DEPLOY_USER /opt/clinomic-monitoring/start-monitoring.sh

# Add to system startup
cat > /etc/systemd/system/clinomic-startup.service << 'EOF'
[Unit]
Description=Clinomic Startup Service
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/opt/clinomic-monitoring/start-monitoring.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl enable clinomic-startup.service
print_success "Startup service created and enabled"

print_header "MONITORING SETUP COMPLETE"
echo ""
echo "Monitoring components installed:"
echo "- Health checks running every minute"
echo "- Log rotation configured"
echo "- Alert handler running every 5 minutes"
echo "- Report generation available"
echo "- Services configured to start on boot"
echo ""
echo "To view the monitoring dashboard:"
echo "sudo -u $DEPLOY_USER /opt/clinomic-monitoring/dashboard.sh"
echo ""
echo "To check health manually:"
echo "sudo -u $DEPLOY_USER /opt/clinomic-monitoring/health-check.sh"
echo ""
echo "To generate a report:"
echo "sudo -u $DEPLOY_USER /opt/clinomic-monitoring/generate-report.sh"
echo ""
echo "Logs are available at: $LOG_PATH/"
echo ""
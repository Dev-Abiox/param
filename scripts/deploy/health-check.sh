#!/bin/bash

# Health Check Script for Clinomic B12 Screening Platform
# Checks the health of deployed services

set -e

DEPLOY_DIR="/opt/clinomic-b12-platform"
LOG_FILE="$DEPLOY_DIR/health-check.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a $LOG_FILE
}

success() {
    echo -e "${GREEN}$1${NC}"
}

warning() {
    echo -e "${YELLOW}$1${NC}"
}

error() {
    echo -e "${RED}$1${NC}"
}

check_backend_health() {
    log "Checking backend health..."
    if curl -f -s http://localhost:8000/api/health/ >/dev/null; then
        success "✓ Backend is healthy"
        return 0
    else
        error "✗ Backend is unhealthy"
        return 1
    fi
}

check_frontend_health() {
    log "Checking frontend health..."
    if curl -f -s http://localhost:3000/ >/dev/null; then
        success "✓ Frontend is healthy"
        return 0
    else
        error "✗ Frontend is unhealthy"
        return 1
    fi
}

check_database_connection() {
    log "Checking database connection..."
    cd $DEPLOY_DIR/$(cat $DEPLOY_DIR/current_env 2>/dev/null || echo "blue")
    
    if docker compose exec db pg_isready >/dev/null 2>&1; then
        success "✓ Database is connected and ready"
        return 0
    else
        error "✗ Database connection failed"
        return 1
    fi
}

check_docker_containers() {
    log "Checking Docker container statuses..."
    cd $DEPLOY_DIR/$(cat $DEPLOY_DIR/current_env 2>/dev/null || echo "blue")
    
    containers=(backend frontend nginx db redis)
    all_healthy=true
    
    for container in "${containers[@]}"; do
        if docker compose ps | grep "$container" | grep -q "Up\|running"; then
            success "✓ $container is running"
        else
            error "✗ $container is not running"
            all_healthy=false
        fi
    done
    
    if [ "$all_healthy" = true ]; then
        return 0
    else
        return 1
    fi
}

check_system_resources() {
    log "Checking system resources..."
    
    # Check disk space (warn if >80% used)
    disk_usage=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ $disk_usage -gt 80 ]; then
        warning "! Disk usage is ${disk_usage}% (high)"
    else
        success "✓ Disk usage is ${disk_usage}% (OK)"
    fi
    
    # Check memory usage
    mem_usage=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100}')
    if [ $mem_usage -gt 80 ]; then
        warning "! Memory usage is ${mem_usage}% (high)"
    else
        success "✓ Memory usage is ${mem_usage}% (OK)"
    fi
}

main() {
    log "Starting health check for Clinomic B12 Screening Platform"
    
    all_checks_passed=true
    
    # Run all health checks
    if ! check_docker_containers; then
        all_checks_passed=false
    fi
    
    if ! check_backend_health; then
        all_checks_passed=false
    fi
    
    if ! check_frontend_health; then
        all_checks_passed=false
    fi
    
    if ! check_database_connection; then
        all_checks_passed=false
    fi
    
    check_system_resources  # This doesn't affect the overall health status
    
    if [ "$all_checks_passed" = true ]; then
        success "✓ All health checks passed"
        log "Health check completed successfully at $(date)"
        exit 0
    else
        error "✗ Some health checks failed"
        log "Health check failed at $(date)"
        exit 1
    fi
}

main "$@"
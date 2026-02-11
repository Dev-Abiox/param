#!/bin/bash

# Rollback Script for Clinomic B12 Screening Platform
# Reverts to the previous deployment in case of failure

set -e

DEPLOY_DIR="/opt/clinomic-b12-platform"
LOG_FILE="$DEPLOY_DIR/rollback.log"

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

main() {
    log "Starting rollback procedure for Clinomic B12 Screening Platform"
    
    # Check if current_env file exists
    if [ ! -f "$DEPLOY_DIR/current_env" ]; then
        error "No current environment file found. Cannot perform rollback."
        exit 1
    fi
    
    # Get current environment
    current_env=$(cat $DEPLOY_DIR/current_env)
    log "Current environment is: $current_env"
    
    # Determine rollback environment (opposite of current)
    if [ "$current_env" = "blue" ]; then
        rollback_env="green"
    elif [ "$current_env" = "green" ]; then
        rollback_env="blue"
    else
        error "Invalid current environment: $current_env"
        exit 1
    fi
    
    log "Attempting to rollback to: $rollback_env"
    
    # Get directories
    current_dir="$DEPLOY_DIR/$current_env"
    rollback_dir="$DEPLOY_DIR/$rollback_env"
    
    # Check if rollback environment exists
    if [ ! -d "$rollback_dir" ]; then
        error "Rollback environment directory does not exist: $rollback_dir"
        exit 1
    fi
    
    # Stop current environment
    log "Stopping current environment ($current_env)..."
    cd "$current_dir"
    docker compose down
    
    # Start rollback environment
    log "Starting rollback environment ($rollback_env)..."
    cd "$rollback_dir"
    docker compose up -d
    
    # Wait for rollback environment to start
    log "Waiting for rollback environment to become healthy..."
    sleep 30
    
    # Verify rollback environment is running
    MAX_RETRIES=10
    retry_count=0
    backend_healthy=false
    
    while [ $retry_count -lt $MAX_RETRIES ]; do
        if curl -f -s http://localhost:8000/api/health/ >/dev/null; then
            backend_healthy=true
            break
        else
            warning "Rollback environment not ready yet, retrying... ($((retry_count + 1))/$MAX_RETRIES)"
            sleep 10
            retry_count=$((retry_count + 1))
        fi
    done
    
    if [ "$backend_healthy" = true ]; then
        # Update current environment to rollback environment
        echo "$rollback_env" > "$DEPLOY_DIR/current_env"
        success "Rollback completed successfully!"
        success "Active environment is now: $rollback_env"
        log "Rollback completed at $(date)"
    else
        error "Rollback environment did not become healthy after $MAX_RETRIES attempts"
        error "Manual intervention required!"
        exit 1
    fi
}

main "$@"
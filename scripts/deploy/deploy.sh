#!/bin/bash
# ============================================================================
# CLINOMIC DEPLOYMENT SCRIPT
# ============================================================================
# Usage: ./deploy.sh [OPTIONS]
# Options:
#   --tag=TAG     Image tag to deploy (default: latest)
#   --skip-pull   Skip pulling images (use local)
#   --force       Force restart even if health check fails
#   --dry-run     Show what would be done without doing it
# ============================================================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/clinomic}"
COMPOSE_FILE="${DEPLOY_PATH}/docker-compose.prod.yml"
HEALTH_URL="http://localhost:8001/api/health/ready"
HEALTH_TIMEOUT=60
LOG_FILE="/var/log/clinomic-deploys.log"

# Parse arguments
TAG="latest"
SKIP_PULL=false
FORCE=false
DRY_RUN=false

for arg in "$@"; do
    case $arg in
        --tag=*)
            TAG="${arg#*=}"
            ;;
        --skip-pull)
            SKIP_PULL=true
            ;;
        --force)
            FORCE=true
            ;;
        --dry-run)
            DRY_RUN=true
            ;;
        *)
            echo "Unknown argument: $arg"
            exit 1
            ;;
    esac
done

# Functions
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$(date -Iseconds) | $1" >> $LOG_FILE
}

check_health() {
    local timeout=$1
    local start_time=$(date +%s)
    
    while true; do
        if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
            return 0
        fi
        
        local elapsed=$(($(date +%s) - start_time))
        if [ $elapsed -ge $timeout ]; then
            return 1
        fi
        
        sleep 1
    done
}

save_state() {
    log "Saving current state for rollback..."
    
    # Save current image tags
    docker images --format "{{.Repository}}:{{.Tag}}" | grep -E "clinomic-(backend|frontend)" | head -2 > "${DEPLOY_PATH}/.last_deploy_images"
    
    # Save compose file
    cp "$COMPOSE_FILE" "${COMPOSE_FILE}.backup"
    
    # Record current commit
    echo "$TAG" > "${DEPLOY_PATH}/.last_deploy_tag"
}

rollback() {
    log "ROLLBACK | Initiating rollback..."
    
    if [ -f "${COMPOSE_FILE}.backup" ]; then
        cp "${COMPOSE_FILE}.backup" "$COMPOSE_FILE"
    fi
    
    docker-compose -f "$COMPOSE_FILE" up -d --force-recreate backend frontend
    
    log "ROLLBACK | Rollback complete"
}

# Main deployment
main() {
    log "=========================================="
    log "CLINOMIC DEPLOYMENT"
    log "=========================================="
    log "Tag: $TAG"
    log "Deploy Path: $DEPLOY_PATH"
    log "Skip Pull: $SKIP_PULL"
    log "Force: $FORCE"
    log "Dry Run: $DRY_RUN"
    log ""
    
    cd "$DEPLOY_PATH"
    
    if [ "$DRY_RUN" = true ]; then
        log "DRY RUN MODE - No changes will be made"
    fi
    
    # Step 1: Pre-deployment health check
    log "Step 1: Pre-deployment health check..."
    if check_health 5; then
        log "Current deployment is healthy"
    else
        log "WARNING: Current deployment is unhealthy!"
        if [ "$FORCE" != true ]; then
            log "Use --force to continue anyway"
            exit 1
        fi
    fi
    
    # Step 2: Save state for rollback
    if [ "$DRY_RUN" != true ]; then
        save_state
    fi
    
    # Step 3: Pull new images
    if [ "$SKIP_PULL" != true ]; then
        log "Step 3: Pulling new images..."
        if [ "$DRY_RUN" != true ]; then
            docker pull "clinomic-backend:$TAG" || docker pull "ghcr.io/dev-abiox/clinomic-prod/backend:$TAG"
            docker pull "clinomic-frontend:$TAG" || docker pull "ghcr.io/dev-abiox/clinomic-prod/frontend:$TAG"
        fi
    fi
    
    # Step 4: Update backend (rolling)
    log "Step 4: Updating backend..."
    if [ "$DRY_RUN" != true ]; then
        docker-compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate backend
    fi
    
    # Step 5: Wait for backend health
    log "Step 5: Waiting for backend health check..."
    if [ "$DRY_RUN" != true ]; then
        if ! check_health $HEALTH_TIMEOUT; then
            log "ERROR: Backend health check failed after ${HEALTH_TIMEOUT}s!"
            rollback
            exit 1
        fi
        log "Backend healthy"
    fi
    
    # Step 6: Update frontend
    log "Step 6: Updating frontend..."
    if [ "$DRY_RUN" != true ]; then
        docker-compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate frontend
    fi
    
    # Step 7: Reload nginx
    log "Step 7: Reloading nginx..."
    if [ "$DRY_RUN" != true ]; then
        docker exec clinomic-nginx nginx -s reload 2>/dev/null || sudo nginx -s reload 2>/dev/null || true
    fi
    
    # Step 8: Final health check
    log "Step 8: Final health verification..."
    if [ "$DRY_RUN" != true ]; then
        sleep 3
        if check_health 10; then
            log "✓ Deployment successful!"
        else
            log "✗ Final health check failed!"
            if [ "$FORCE" != true ]; then
                rollback
                exit 1
            fi
        fi
    fi
    
    # Step 9: Cleanup
    log "Step 9: Cleaning up old images..."
    if [ "$DRY_RUN" != true ]; then
        docker image prune -f --filter "until=168h" || true
    fi
    
    log ""
    log "=========================================="
    log "DEPLOYMENT COMPLETE"
    log "=========================================="
}

# Run main
main "$@"

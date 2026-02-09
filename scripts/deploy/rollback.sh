#!/bin/bash
# ============================================================================
# CLINOMIC ROLLBACK SCRIPT
# ============================================================================
# Usage: ./rollback.sh [OPTIONS]
# Options:
#   --to=TARGET   Rollback target: previous, sha-xxx, or image tag
#   --force       Force rollback without confirmation
#   --dry-run     Show what would be done
# ============================================================================

set -e

# Configuration
DEPLOY_PATH="${DEPLOY_PATH:-/opt/clinomic}"
COMPOSE_FILE="${DEPLOY_PATH}/docker-compose.prod.yml"
HEALTH_URL="http://localhost:8001/api/health/ready"
LOG_FILE="/var/log/clinomic-deploys.log"

# Parse arguments
TARGET="previous"
FORCE=false
DRY_RUN=false

for arg in "$@"; do
    case $arg in
        --to=*)
            TARGET="${arg#*=}"
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

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$(date -Iseconds) | ROLLBACK | $1" >> $LOG_FILE
}

log "=========================================="
log "CLINOMIC ROLLBACK"
log "=========================================="
log "Target: $TARGET"
log ""

cd "$DEPLOY_PATH"

# Confirmation
if [ "$FORCE" != true ] && [ "$DRY_RUN" != true ]; then
    read -p "Are you sure you want to rollback to '$TARGET'? (yes/no): " confirm
    if [ "$confirm" != "yes" ]; then
        log "Rollback cancelled"
        exit 0
    fi
fi

if [ "$TARGET" == "previous" ]; then
    log "Rolling back to previous deployment..."
    
    if [ ! -f "${DEPLOY_PATH}/.last_deploy_images" ]; then
        log "ERROR: No previous deployment record found!"
        exit 1
    fi
    
    log "Previous images:"
    cat "${DEPLOY_PATH}/.last_deploy_images"
    
    if [ "$DRY_RUN" != true ]; then
        # Restore previous compose file
        if [ -f "${COMPOSE_FILE}.backup" ]; then
            cp "${COMPOSE_FILE}.backup" "$COMPOSE_FILE"
        fi
        
        # Restart with previous images
        docker-compose -f "$COMPOSE_FILE" up -d --force-recreate backend frontend
    fi
    
else
    log "Rolling back to specific version: $TARGET"
    
    if [ "$DRY_RUN" != true ]; then
        # Pull specific version
        docker pull "ghcr.io/dev-abiox/clinomic-prod/backend:$TARGET"
        docker pull "ghcr.io/dev-abiox/clinomic-prod/frontend:$TARGET"
        
        # Tag as latest
        docker tag "ghcr.io/dev-abiox/clinomic-prod/backend:$TARGET" clinomic-backend:latest
        docker tag "ghcr.io/dev-abiox/clinomic-prod/frontend:$TARGET" clinomic-frontend:latest
        
        # Restart
        docker-compose -f "$COMPOSE_FILE" up -d --force-recreate backend frontend
    fi
fi

# Health check
log "Waiting for health check..."
if [ "$DRY_RUN" != true ]; then
    sleep 5
    for i in {1..30}; do
        if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
            log "✓ Health check passed"
            break
        fi
        if [ $i -eq 30 ]; then
            log "✗ Health check failed after rollback!"
            exit 1
        fi
        sleep 1
    done
    
    # Reload nginx
    docker exec clinomic-nginx nginx -s reload 2>/dev/null || sudo nginx -s reload 2>/dev/null || true
fi

log ""
log "=========================================="
log "ROLLBACK COMPLETE"
log "=========================================="

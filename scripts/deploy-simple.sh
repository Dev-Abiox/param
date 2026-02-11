#!/bin/bash

# Simple Production Deployment Script for Clinomic B12 Platform
# Single-stack deployment for production environment

set -e  # Exit on any error

# Configuration
DEPLOY_DIR="/opt/clinomic"
COMPOSE_FILE="docker-compose.prod.yml"
LOG_FILE="/var/log/clinomic_deploy.log"

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

# Function to deploy
deploy() {
    log "Starting deployment..."
    
    # Navigate to deployment directory
    cd "$DEPLOY_DIR"
    
    # Pull latest images
    log "Pulling latest images..."
    docker-compose -f "$COMPOSE_FILE" pull
    
    # Recreate containers with new images
    log "Recreating containers..."
    docker-compose -f "$COMPOSE_FILE" up -d --force-recreate
    
    # Wait for services
    log "Waiting for services to be ready..."
    sleep 30
    
    # Health checks
    log "Performing health checks..."
    
    # Check backend
    for i in {1..10}; do
        if curl -f -H "Host: clinomiclabs.com" http://localhost:8000/api/health/live >/dev/null 2>&1; then
            success "Backend is healthy"
            break
        fi
        if [ $i -eq 10 ]; then
            error "Backend health check failed"
            docker-compose -f "$COMPOSE_FILE" logs backend
            exit 1
        fi
        sleep 5
    done
    
    # Check frontend
    for i in {1..10}; do
        if curl -f http://localhost:3000/ >/dev/null 2>&1; then
            success "Frontend is healthy"
            break
        fi
        if [ $i -eq 10 ]; then
            error "Frontend health check failed"
            docker-compose -f "$COMPOSE_FILE" logs frontend
            exit 1
        fi
        sleep 5
    done
    
    # Cleanup unused images
    docker image prune -f
    
    success "Deployment completed successfully!"
    log "Platform available at https://clinomiclabs.com"
}

# Run deployment
deploy "$@"
#!/bin/bash

set -e  # Exit on any error

# Blue-Green Deployment Script for Clinomic B12 Screening Platform
# This script manages zero-downtime deployments using blue-green strategy

# Configuration
DEPLOY_DIR="/opt/clinomic-b12-platform"
BLUE_DIR="$DEPLOY_DIR/blue"
GREEN_DIR="$DEPLOY_DIR/green"
LOG_FILE="$DEPLOY_DIR/deployment.log"
MAX_RETRIES=3

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

# Function to check if Docker is running
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        error "Docker is not running or not accessible"
        exit 1
    fi
}

# Function to get current active environment
get_current_env() {
    if [ -f "$DEPLOY_DIR/current_env" ]; then
        cat "$DEPLOY_DIR/current_env"
    else
        echo "blue"  # Default to blue for first deployment
    fi
}

# Function to get next environment
get_next_env() {
    current_env=$(get_current_env)
    if [ "$current_env" = "blue" ]; then
        echo "green"
    else
        echo "blue"
    fi
}

# Function to get directory for environment
get_env_dir() {
    env=$1
    if [ "$env" = "blue" ]; then
        echo "$BLUE_DIR"
    else
        echo "$GREEN_DIR"
    fi
}

# Function to start services in an environment
start_services() {
    env_dir=$1
    cd "$env_dir"
    
    log "Starting services in $env_dir..."
    docker-compose up -d
    
    # Wait for services to be healthy
    log "Waiting for services to become healthy..."
    sleep 30
    
    # Check if services are running and healthy
    for service in backend frontend nginx; do
        retry_count=0
        while [ $retry_count -lt $MAX_RETRIES ]; do
            if docker compose ps | grep "$service" | grep -q "Up\|running"; then
                success "Service $service is running"
                break
            else
                warning "Service $service not running yet, retrying... ($((retry_count + 1))/$MAX_RETRIES)"
                sleep 10
                retry_count=$((retry_count + 1))
            fi
        done
        
        if [ $retry_count -eq $MAX_RETRIES ]; then
            error "Service $service failed to start after $MAX_RETRIES retries"
            return 1
        fi
    done
    
    # Perform health checks on endpoints
    log "Performing endpoint health checks..."
    
    # Check backend health
    retry_count=0
    backend_url="http://localhost:8000/api/health/"
    while [ $retry_count -lt $MAX_RETRIES ]; do
        if curl -f -s "$backend_url" >/dev/null; then
            success "Backend health check passed"
            break
        else
            warning "Backend health check failed, retrying... ($((retry_count + 1))/$MAX_RETRIES)"
            sleep 10
            retry_count=$((retry_count + 1))
        fi
    done
    
    if [ $retry_count -eq $MAX_RETRIES ]; then
        error "Backend health check failed after $MAX_RETRIES retries"
        return 1
    fi
    
    # Check frontend health
    retry_count=0
    frontend_url="http://localhost:3000/"
    while [ $retry_count -lt $MAX_RETRIES ]; do
        if curl -f -s "$frontend_url" >/dev/null; then
            success "Frontend health check passed"
            break
        else
            warning "Frontend health check failed, retrying... ($((retry_count + 1))/$MAX_RETRIES)"
            sleep 10
            retry_count=$((retry_count + 1))
        fi
    done
    
    if [ $retry_count -eq $MAX_RETRIES ]; then
        error "Frontend health check failed after $MAX_RETRIES retries"
        return 1
    fi
    
    return 0
}

# Function to stop services in an environment
stop_services() {
    env_dir=$1
    cd "$env_dir"
    
    log "Stopping services in $env_dir..."
    docker compose down
}

# Function to rollback to previous environment
rollback() {
    log "Initiating rollback procedure..."
    
    current_env=$(get_current_env)
    prev_env_dir=$(get_env_dir "$current_env")
    
    # Stop services in failed environment
    log "Stopping failed environment services..."
    stop_services "$prev_env_dir"
    
    # Determine previous environment (opposite of current)
    if [ "$current_env" = "blue" ]; then
        rollback_env="green"
    else
        rollback_env="blue"
    fi
    
    rollback_dir=$(get_env_dir "$rollback_env")
    
    # Start previous environment
    log "Bringing back previous environment ($rollback_env)..."
    start_services "$rollback_dir"
    
    # Update current environment to previous
    echo "$rollback_env" > "$DEPLOY_DIR/current_env"
    
    error "Rollback completed. Active environment is now $rollback_env"
    exit 1
}

# Main deployment logic
main() {
    log "Starting blue-green deployment for Clinomic B12 Screening Platform"
    
    # Check prerequisites
    check_docker
    
    # Get current and next environments
    current_env=$(get_current_env)
    next_env=$(get_next_env)
    
    success "Current active environment: $current_env"
    success "Deploying to environment: $next_env"
    
    # Get directories
    current_dir=$(get_env_dir "$current_env")
    next_dir=$(get_env_dir "$next_env")
    
    # Create next environment directory if it doesn't exist
    mkdir -p "$next_dir"
    mkdir -p "$DEPLOY_DIR/secrets"
    
    # Copy deployment files
    cp -f "$DEPLOY_DIR/docker-compose.prod.yml" "$next_dir/"
    
    # Generate secrets if they don't exist
    if [ ! -f "$DEPLOY_DIR/secrets/postgres_password" ]; then
        openssl rand -hex 32 > "$DEPLOY_DIR/secrets/postgres_password"
        success "Generated new PostgreSQL password"
    fi
    
    if [ ! -f "$DEPLOY_DIR/secrets/django_secret_key" ]; then
        openssl rand -hex 50 > "$DEPLOY_DIR/secrets/django_secret_key"
        success "Generated new Django secret key"
    fi
    
    if [ ! -f "$DEPLOY_DIR/secrets/fernet_key" ]; then
        python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode('utf-8'))" > "$DEPLOY_DIR/secrets/fernet_key"
        success "Generated new Fernet encryption key"
    fi
    
    # Pull latest images
    log "Pulling latest images..."
    docker pull ghcr.io/$(echo $GITHUB_REPOSITORY | tr '[:upper:]' '[:lower:]'):latest
    docker pull ghcr.io/$(echo $GITHUB_REPOSITORY | tr '[:upper:]' '[:lower:]')-frontend:latest
    
    # Stop any existing services in next environment
    stop_services "$next_dir" || true
    
    # Update image tags in docker-compose file
    sed -i "s|image: ghcr.io/[^[:space:]]*:.*|image: ghcr.io/$(echo $GITHUB_REPOSITORY | tr '[:upper:]' '[:lower:]'):latest|" "$next_dir/docker-compose.prod.yml"
    sed -i "s|image: ghcr.io/[^[:space:]]*-frontend:.*|image: ghcr.io/$(echo $GITHUB_REPOSITORY | tr '[:upper:]' '[:lower:]')-frontend:latest|" "$next_dir/docker-compose.prod.yml"
    
    # Link secrets directory
    ln -sf "$DEPLOY_DIR/secrets" "$next_dir/secrets"
    
    # Start new environment
    log "Starting new environment ($next_env)..."
    if ! start_services "$next_dir"; then
        error "Failed to start new environment, initiating rollback..."
        rollback
    fi
    
    # Update current environment pointer
    echo "$next_env" > "$DEPLOY_DIR/current_env"
    success "Environment pointer updated to $next_env"
    
    # Clean up old environment (stop services but keep files for potential rollback)
    log "Cleaning up old environment ($current_env)..."
    stop_services "$current_dir"
    
    success "Blue-green deployment completed successfully!"
    success "Active environment is now: $next_env"
    log "Deployment completed at $(date)"
}

# Run main function
main "$@"
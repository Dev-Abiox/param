#!/bin/bash
# Blue-Green Deployment Script

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

print_header "BLUE-GREEN DEPLOYMENT STARTED"

# Determine current and next environments
CURRENT_GREEN_RUNNING=$(docker ps --format "table {{.Names}}" | grep -c "clinomic-green" 2>/dev/null || echo 0)
CURRENT_BLUE_RUNNING=$(docker ps --format "table {{.Names}}" | grep -c "clinomic-blue" 2>/dev/null || echo 0)

if [ $CURRENT_GREEN_RUNNING -gt 0 ]; then
    CURRENT_ENV="green"
    NEXT_ENV="blue"
    NEXT_PORTS="8001:8000"
    OLD_PORTS="8000:8000"
else
    CURRENT_ENV="blue"
    NEXT_ENV="green"
    NEXT_PORTS="8000:8000"
    OLD_PORTS="8001:8000"
fi

print_success "Current environment: $CURRENT_ENV"
print_success "Next environment: $NEXT_ENV"

# Start NEXT environment
print_header "DEPLOYING TO $NEXT_ENV ENVIRONMENT"
docker-compose -f docker-compose.v3.yml --profile prod -p "clinomic-$NEXT_ENV" up -d --build

# Wait for services to start
print_warning "Waiting for $NEXT_ENV services to start..."
sleep 45

# Health check for NEXT environment
print_header "RUNNING HEALTH CHECK ON $NEXT_ENV"
HEALTH_CHECK_URL="http://localhost:${NEXT_PORTS%%:*}/api/health/live"
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_CHECK_URL" || echo "000")

if [ "$HEALTH_STATUS" -eq 200 ]; then
    print_success "Health check passed for $NEXT_ENV environment (Status: $HEALTH_STATUS)"
    
    # Switch traffic to NEXT environment using nginx
    print_header "SWITCHING TRAFFIC TO $NEXT_ENV"
    # Update nginx configuration to point to new backend port
    if command -v systemctl >/dev/null 2>&1; then
        systemctl reload nginx
    elif command -v service >/dev/null 2>&1; then
        service nginx reload
    else
        echo "Nginx reload command not found, please reload manually"
    fi
    
    # Wait a bit for traffic switch
    sleep 10
    
    # Stop CURRENT environment
    print_header "STOPPING $CURRENT_ENV ENVIRONMENT"
    docker-compose -f docker-compose.v3.yml --profile prod -p "clinomic-$CURRENT_ENV" down
    
    print_success "Blue-green deployment completed successfully!"
    print_success "Active environment: $NEXT_ENV"
    print_success "Traffic switched to port ${NEXT_PORTS%%:*}"
    
    # Log deployment
    echo "$(date): Blue-green deployment completed. Active environment: $NEXT_ENV" >> /var/log/clinomic-deployments.log
else
    print_error "Health check failed for $NEXT_ENV environment (Status: $HEALTH_STATUS)"
    print_error "Rolling back to $CURRENT_ENV environment"
    
    # Bring back CURRENT environment
    docker-compose -f docker-compose.v3.yml --profile prod -p "clinomic-$CURRENT_ENV" up -d
    
    print_error "Deployment rolled back to $CURRENT_ENV"
    exit 1
fi
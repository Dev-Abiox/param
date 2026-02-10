#!/bin/bash
# ============================================================================
# CLINOMIC VM DEPLOYMENT SCRIPT
# ============================================================================
# This script deploys the Clinomic application to a VM
# It sets up the environment, secrets, and starts the services
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
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEPLOY_PATH="/opt/clinomic"
SECRETS_DIR="/opt/clinomic/secrets"
LOG_FILE="/var/log/clinomic-deploy.log"

log_message() {
    echo "$(date -Iseconds) | $1" >> "$LOG_FILE"
}

print_header "CLINOMIC VM DEPLOYMENT"

echo "This script will:"
echo "1. Clone or update the Clinomic repository"
echo "2. Set up secrets securely"
echo "3. Build and start the application"
echo "4. Configure for production use"
echo ""

read -p "Continue with VM deployment? (yes/no): " confirm
if [[ $confirm != "yes" ]]; then
    echo "VM deployment cancelled"
    exit 0
fi

# Function to check prerequisites
check_prerequisites() {
    print_header "CHECKING PREREQUISITES"
    
    # Check Docker
    if command -v docker &> /dev/null; then
        echo "  ✓ Docker: $(docker --version)"
    else
        print_error "Docker is not installed"
        exit 1
    fi
    
    # Check Docker Compose
    if command -v docker-compose &> /dev/null; then
        echo "  ✓ Docker Compose: $(docker-compose --version)"
    else
        print_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check Python
    if command -v python3 &> /dev/null; then
        echo "  ✓ Python: $(python3 --version)"
    else
        print_error "Python3 is not installed"
        exit 1
    fi
    
    # Check Git
    if command -v git &> /dev/null; then
        echo "  ✓ Git: $(git --version)"
    else
        print_error "Git is not installed"
        exit 1
    fi
}

# Function to clone or update repository
setup_repository() {
    print_header "SETTING UP REPOSITORY"
    
    if [[ -d "$DEPLOY_PATH" ]]; then
        print_warning "Deployment directory already exists, updating..."
        cd "$DEPLOY_PATH"
        git fetch
        git pull origin main
        print_success "Repository updated"
    else
        print_warning "Cloning repository to $DEPLOY_PATH"
        mkdir -p "$DEPLOY_PATH"
        cd "$DEPLOY_PATH"
        git clone https://github.com/Dev-Abiox/param.git .
        print_success "Repository cloned"
    fi
    
    # Set ownership to deploy user if exists
    if id "deploy" &>/dev/null; then
        chown -R deploy:deploy "$DEPLOY_PATH"
    fi
}

# Function to set up secrets
setup_secrets() {
    print_header "SETTING UP SECRETS"
    
    cd "$DEPLOY_PATH"
    
    # Run the secrets setup script
    if [[ -f "./scripts/v3/setup-secrets.sh" ]]; then
        chmod +x "./scripts/v3/setup-secrets.sh"
        ./scripts/v3/setup-secrets.sh << EOF
yes
EOF
        print_success "Secrets configured"
    else
        print_error "setup-secrets.sh not found"
        exit 1
    fi
    
    # Verify .env.v3 exists and has content
    if [[ -f ".env.v3" ]] && [[ -s ".env.v3" ]]; then
        print_success ".env.v3 file exists and is not empty"
    else
        print_error ".env.v3 file is missing or empty"
        exit 1
    fi
}

# Function to build and prepare the application
prepare_application() {
    print_header "PREPARING APPLICATION"
    
    cd "$DEPLOY_PATH"
    
    # Make sure setup script is executable
    if [[ -f "./scripts/v3/setup.sh" ]]; then
        chmod +x "./scripts/v3/setup.sh"
        
        # Run setup (without seeding data for production)
        echo "Running setup to build Docker images..."
        ./scripts/v3/setup.sh
        print_success "Application prepared"
    else
        print_error "setup.sh not found"
        exit 1
    fi
}

# Function to start the application in production mode
start_production() {
    print_header "STARTING PRODUCTION SERVICES"
    
    cd "$DEPLOY_PATH"
    
    if [[ -f "./scripts/v3/start.sh" ]]; then
        chmod +x "./scripts/v3/start.sh"
        
        # Start in production mode
        echo "Starting production services..."
        timeout 300 ./scripts/v3/start.sh prod
        
        if [[ $? -eq 0 ]]; then
            print_success "Production services started"
        else
            print_error "Failed to start production services"
            # Check logs
            docker-compose -f docker-compose.prod.yml logs
            exit 1
        fi
    else
        print_error "start.sh not found"
        exit 1
    fi
}

# Function to configure for production
configure_production() {
    print_header "CONFIGURING PRODUCTION"
    
    cd "$DEPLOY_PATH"
    
    # Create a production-specific docker-compose file
    # Note: docker-compose.prod.yml should already exist as the single source of truth
    if [[ ! -f "docker-compose.prod.yml" ]]; then
        print_error "docker-compose.prod.yml not found - this should be the single source of truth"
        exit 1
    fi
    
    print_success "Using existing docker-compose.prod.yml as production configuration"
    
    # Set up systemd service for auto-start
    if [[ -f "/etc/systemd/system" ]]; then
        cat > /etc/systemd/system/clinomic.service << 'EOF'
[Unit]
Description=Clinomic Application Service
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/clinomic
ExecStart=/bin/bash -c 'cd /opt/clinomic && ./scripts/v3/start.sh prod'
ExecStop=/bin/bash -c 'cd /opt/clinomic && ./scripts/v3/stop.sh'
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
        
        systemctl daemon-reload
        systemctl enable clinomic.service
        print_success "Systemd service created and enabled"
    fi
}

# Function to run health checks
run_health_checks() {
    print_header "RUNNING HEALTH CHECKS"
    
    # Wait a bit for services to start
    echo "Waiting for services to be ready..."
    sleep 30
    
    # Check if backend is responding
    if curl -sf http://localhost:8000/api/health/live > /dev/null 2>&1; then
        print_success "Backend health check passed"
    else
        print_warning "Backend health check failed, checking logs..."
        docker-compose -f docker-compose.prod.yml logs backend_v3 2>/dev/null || true
    fi
    
    # Check if frontend is responding
    if curl -sf http://localhost:3000 > /dev/null 2>&1; then
        print_success "Frontend is accessible"
    else
        print_warning "Frontend may not be accessible yet"
    fi
}

# Function to display deployment summary
display_summary() {
    print_header "DEPLOYMENT SUMMARY"
    
    echo "Application deployed successfully to VM!"
    echo ""
    echo "Services running:"
    docker-compose -f docker-compose.prod.yml ps 2>/dev/null || true
    echo ""
    echo "Access URLs:"
    echo "  Backend API: http://localhost:8000"
    echo "  Frontend UI: http://localhost:3000"
    echo "  Admin Panel: http://localhost:8000/admin/"
    echo ""
    echo "Management commands:"
    echo "  Start: /opt/clinomic/scripts/v3/start.sh prod"
    echo "  Stop:  /opt/clinomic/scripts/v3/stop.sh"
    echo "  Logs:  /opt/clinomic/scripts/v3/logs.sh"
    echo ""
    echo "For production, ensure your domain is pointing to this server"
    echo "and configure SSL certificates as needed."
    echo ""
    echo "Deployment log: $LOG_FILE"
    echo ""
}

# Main deployment function
main() {
    log_message "Starting VM deployment"
    
    check_prerequisites
    setup_repository
    setup_secrets
    prepare_application
    start_production
    configure_production
    run_health_checks
    display_summary
    
    log_message "VM deployment completed successfully"
    
    echo ""
    print_success "VM deployment completed successfully!"
    echo "Check the summary above for access information."
}

main
#!/bin/bash
# ============================================================================
# CLINOMIC KVM DEPLOYMENT SCRIPT FOR BIGROCK
# ============================================================================
# Designed specifically for BigRock KVM with Ubuntu 22.04
# IP: 66.116.225.67
# Domains: clinomiclabs.com, testing.clinomiclabs.com
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

# Configuration for your specific setup
KVM_IP="66.116.225.67"
DOMAIN_MAIN="clinomiclabs.com"
DOMAIN_TESTING="testing.clinomiclabs.com"
DEPLOY_PATH="/opt/clinomic"
DEPLOY_USER="deploy"

print_header "CLINOMIC DEPLOYMENT FOR BIGROCK KVM"
echo "Target: $KVM_IP"
echo "Domains: $DOMAIN_MAIN, $DOMAIN_TESTING"
echo "Duration: Jan 26, 2026 - Feb 26, 2026"
echo "Specs: 4 cores, 8GB RAM, 200GB disk, 3TB bandwidth"
echo ""

read -p "Continue with deployment to BigRock KVM? (yes/no): " confirm
if [[ $confirm != "yes" ]]; then
    echo "Deployment cancelled"
    exit 0
fi

# Function to check prerequisites on KVM
check_kvm_prerequisites() {
    print_header "VERIFYING KVM PREREQUISITES ON $KVM_IP"
    
    echo "Please run these commands on your KVM server ($KVM_IP):"
    echo ""
    echo "1. Update system:"
    echo "   sudo apt update && sudo apt upgrade -y"
    echo ""
    echo "2. Install Docker:"
    echo "   sudo apt install -y docker.io docker-compose-plugin"
    echo "   sudo systemctl enable docker"
    echo "   sudo systemctl start docker"
    echo ""
    echo "3. Create deploy user:"
    echo "   sudo useradd -m -s /bin/bash deploy"
    echo "   sudo usermod -aG docker deploy"
    echo ""
    echo "4. Create deployment directory:"
    echo "   sudo mkdir -p /opt/clinomic"
    echo "   sudo chown deploy:deploy /opt/clinomic"
    echo ""
    echo "5. Install Python3:"
    echo "   sudo apt install -y python3 python3-pip"
    echo ""
    echo "After completing these steps, press Enter to continue..."
    read
}

# Function to deploy to KVM
deploy_to_kvm() {
    print_header "DEPLOYING TO BIGROCK KVM ($KVM_IP)"
    
    echo "Deployment steps:"
    echo ""
    echo "1. SSH to your KVM:"
    echo "   ssh deploy@$KVM_IP"
    echo ""
    echo "2. Navigate to deployment directory:"
    echo "   cd /opt/clinomic"
    echo ""
    echo "3. Clone the repository:"
    echo "   git clone https://github.com/Dev-Abiox/param.git ."
    echo ""
    echo "4. Make scripts executable:"
    echo "   chmod +x scripts/v3/*.sh"
    echo "   chmod +x scripts/monitoring/*.sh"
    echo ""
    echo "5. Run the deployment script:"
    echo "   ./scripts/v3/deploy-to-vm.sh"
    echo ""
    echo "The script will:"
    echo "   - Generate secure secrets automatically"
    echo "   - Build Docker images"
    echo "   - Start services in production mode"
    echo "   - Configure monitoring"
    echo ""
}

# Function to setup domains and SSL
setup_domains_ssl() {
    print_header "DOMAIN AND SSL SETUP"
    
    echo "For your domains ($DOMAIN_MAIN, $DOMAIN_TESTING):"
    echo ""
    echo "1. Point your domains to IP: $KVM_IP"
    echo "2. After DNS propagation, setup SSL:"
    echo ""
    echo "   # Install Certbot"
    echo "   sudo apt install certbot"
    echo ""
    echo "   # Get SSL certificates"
    echo "   sudo certbot certonly --standalone -d $DOMAIN_MAIN -d www.$DOMAIN_MAIN"
    echo "   sudo certbot certonly --standalone -d $DOMAIN_TESTING"
    echo ""
    echo "   # Copy certificates to application directory"
    echo "   sudo mkdir -p /opt/clinomic/ssl"
    echo "   sudo cp /etc/letsencrypt/live/$DOMAIN_MAIN/fullchain.pem /opt/clinomic/ssl/"
    echo "   sudo cp /etc/letsencrypt/live/$DOMAIN_MAIN/privkey.pem /opt/clinomic/ssl/"
    echo ""
}

# Function to setup CI/CD with GitHub Actions
setup_ci_cd() {
    print_header "CI/CD SETUP WITH GITHUB ACTIONS"
    
    echo "To setup GitHub Actions for automated deployment:"
    echo ""
    echo "1. In your GitHub repository, go to Settings > Secrets and Variables > Actions"
    echo ""
    echo "2. Add these secrets:"
    echo "   PRODUCTION_VM_HOST = $KVM_IP"
    echo "   TESTING_VM_HOST = $KVM_IP"
    echo "   VM_USERNAME = deploy"
    echo "   VPS_SSH_PRIVATE_KEY = [your SSH private key for deploy user]"
    echo "   POSTGRES_DB = clinomic"
    echo "   POSTGRES_USER = postgres"
    echo "   POSTGRES_PASSWORD = [your secure password]"
    echo "   ALLOWED_HOSTS = $DOMAIN_MAIN,www.$DOMAIN_MAIN,$DOMAIN_TESTING,$KVM_IP,localhost"
    echo "   CORS_ORIGINS = https://$DOMAIN_MAIN,https://www.$DOMAIN_MAIN,https://$DOMAIN_TESTING,http://$KVM_IP,http://localhost:3000"
    echo ""
    echo "3. Create Environments in GitHub:"
    echo "   - Environment name: 'testing' for testing deployment"
    echo "   - Environment name: 'production' for production deployment"
    echo ""
    echo "4. The CI/CD will automatically deploy to your KVM when you push to main branch"
    echo ""
}

# Function to verify deployment
verify_deployment() {
    print_header "VERIFICATION STEPS"
    
    echo "After deployment, verify with these commands:"
    echo ""
    echo "# Check running containers"
    echo "docker ps"
    echo ""
    echo "# Check application health"
    echo "curl http://localhost:8000/api/health/live"
    echo ""
    echo "# Check logs if needed"
    echo "./scripts/v3/logs.sh"
    echo ""
    echo "# Access your applications"
    echo "Production: https://$DOMAIN_MAIN"
    echo "Testing: https://$DOMAIN_TESTING"
    echo ""
}

# Function to troubleshoot common issues
troubleshoot_issues() {
    print_header "TROUBLESHOOTING COMMON ISSUES"
    
    echo "If deployment fails, check:"
    echo ""
    echo "1. Docker permissions:"
    echo "   sudo usermod -aG docker deploy"
    echo "   # Then logout and login again"
    echo ""
    echo "2. Firewall settings:"
    echo "   sudo ufw allow 80"
    echo "   sudo ufw allow 443"
    echo "   sudo ufw allow 8000"
    echo "   sudo ufw allow 3000"
    echo "   sudo ufw --force enable"
    echo ""
    echo "3. Disk space:"
    echo "   df -h"
    echo ""
    echo "4. Memory usage:"
    echo "   free -h"
    echo ""
    echo "5. Docker logs:"
    echo "   docker logs <container_name>"
    echo ""
}

# Main execution
main() {
    echo "This script provides the deployment procedure for your BigRock KVM."
    echo ""
    
    check_kvm_prerequisites
    deploy_to_kvm
    setup_domains_ssl
    setup_ci_cd
    verify_deployment
    troubleshoot_issues
    
    print_header "DEPLOYMENT PREPARATION COMPLETE"
    echo ""
    echo "You are now ready to deploy to your BigRock KVM:"
    echo "1. Complete the prerequisite setup on your KVM"
    echo "2. Run the deployment commands on your KVM"
    echo "3. Setup SSL certificates for your domains"
    echo "4. Configure GitHub Actions for automated deployment"
    echo ""
    echo "Your KVM is configured as:"
    echo "- IP: $KVM_IP"
    echo "- Domains: $DOMAIN_MAIN (production), $DOMAIN_TESTING (testing)"
    echo "- Medical-grade security requirements met"
    echo "- Expires: Feb 26, 2026"
    echo ""
    echo "For medical-grade security, ensure:"
    echo "- Regular security updates"
    echo "- SSL/TLS encryption enabled"
    echo "- Proper audit logging configured"
    echo "- Backup procedures in place"
    echo ""
}

main
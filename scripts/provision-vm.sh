#!/bin/bash
# ============================================================================
# CLINOMIC VM PROVISIONING SCRIPT
# ============================================================================
# This script provisions a VM for hosting the Clinomic B12 Screening Platform
# Sets up Docker, creates deploy user, configures firewall, and prepares
# the environment for CI/CD deployments
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
TESTING_DEPLOY_PATH="/opt/clinomic-testing"
SSL_PATH="$DEPLOY_PATH/ssl"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    print_error "This script must be run as root"
    exit 1
fi

print_header "CLINOMIC VM PROVISIONING"

echo "This script will:"
echo "1. Update system packages"
echo "2. Install Docker and Docker Compose"
echo "3. Create deploy user with limited permissions"
echo "4. Configure firewall"
echo "5. Create deployment directories"
echo "6. Set up SSL certificate directory"
echo ""

read -p "Continue with provisioning? (yes/no): " confirm
if [[ $confirm != "yes" ]]; then
    echo "Provisioning cancelled"
    exit 0
fi

# Update system
print_header "UPDATING SYSTEM PACKAGES"
apt-get update
apt-get upgrade -y
print_success "System updated"

# Install prerequisites
print_header "INSTALLING PREREQUISITES"
apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    ufw \
    certbot \
    nginx \
    python3-certbot-nginx
print_success "Prerequisites installed"

# Install Docker
print_header "INSTALLING DOCKER"
if ! command -v docker &> /dev/null; then
    # Add Docker's official GPG key
    mkdir -p /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    
    # Set up the repository
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    
    # Install Docker Engine
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    print_success "Docker installed and enabled"
else
    print_warning "Docker already installed"
fi

# Create deploy user
print_header "CREATING DEPLOY USER"
if id "$DEPLOY_USER" &>/dev/null; then
    print_warning "User $DEPLOY_USER already exists"
else
    useradd -m -s /bin/bash $DEPLOY_USER
    print_success "Created user: $DEPLOY_USER"
fi

# Create deployment directories
print_header "SETTING UP DEPLOYMENT DIRECTORIES"
mkdir -p $DEPLOY_PATH
mkdir -p $TESTING_DEPLOY_PATH
mkdir -p $SSL_PATH
mkdir -p /var/log/clinomic

chown -R $DEPLOY_USER:$DEPLOY_USER $DEPLOY_PATH
chown -R $DEPLOY_USER:$DEPLOY_USER $TESTING_DEPLOY_PATH
chown -R $DEPLOY_USER:$DEPLOY_USER $SSL_PATH
chown -R $DEPLOY_USER:$DEPLOY_USER /var/log/clinomic
print_success "Deployment directories created"

# Setup SSH for deploy user
print_header "CONFIGURING SSH FOR DEPLOY USER"
mkdir -p /home/$DEPLOY_USER/.ssh
chmod 700 /home/$DEPLOY_USER/.ssh

# Create authorized_keys file if it doesn't exist
if [[ ! -f /home/$DEPLOY_USER/.ssh/authorized_keys ]]; then
    touch /home/$DEPLOY_USER/.ssh/authorized_keys
fi
chmod 600 /home/$DEPLOY_USER/.ssh/authorized_keys
chown -R $DEPLOY_USER:$DEPLOY_USER /home/$DEPLOY_USER/.ssh
print_success "SSH configured for deploy user"

# Add deploy user to docker group
usermod -aG docker $DEPLOY_USER
print_success "Added $DEPLOY_USER to docker group"

# Configure firewall
print_header "CONFIGURING FIREWALL"
ufw --force reset

# Allow SSH (important to not lock ourselves out)
ufw allow 22/tcp
print_success "SSH access allowed"

# Allow HTTP and HTTPS
ufw allow 80/tcp
ufw allow 443/tcp
print_success "HTTP/HTTPS access allowed"

# Allow application ports
ufw allow 8000/tcp  # Backend API
ufw allow 3000/tcp  # Frontend
print_success "Application ports allowed"

# Enable firewall
ufw --force enable
print_success "Firewall enabled"

# Create sudoers entries for deploy user
print_header "CONFIGURING SUDO PERMISSIONS"
cat > /etc/sudoers.d/deploy << 'EOF'
# Deploy user limited sudo access
deploy ALL=(ALL) NOPASSWD: /usr/bin/docker *
deploy ALL=(ALL) NOPASSWD: /usr/bin/docker-compose *
deploy ALL=(ALL) NOPASSWD: /usr/sbin/nginx -s reload
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload nginx
deploy ALL=(ALL) NOPASSWD: /usr/bin/certbot *
deploy ALL=(ALL) NOPASSWD: /bin/systemctl start docker
deploy ALL=(ALL) NOPASSWD: /bin/systemctl stop docker
deploy ALL=(ALL) NOPASSWD: /bin/systemctl restart docker
EOF
chmod 440 /etc/sudoers.d/deploy
print_success "Sudo permissions configured"

# Create example docker-compose files
print_header "CREATING EXAMPLE CONFIGURATION FILES"

# Production docker-compose file
cat > $DEPLOY_PATH/docker-compose.prod.yml << 'EOF'
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    restart: always
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-clinomic}
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    image: ghcr.io/YOUR_USERNAME/clinomic-backend:latest
    restart: always
    environment:
      - DEBUG=False
      - APP_ENV=production
      - POSTGRES_HOST=db
      - POSTGRES_PORT=5432
      - POSTGRES_DB=${POSTGRES_DB:-clinomic}
      - POSTGRES_USER=${POSTGRES_USER:-postgres}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - JWT_REFRESH_SECRET_KEY=${JWT_REFRESH_SECRET_KEY}
      - MASTER_ENCRYPTION_KEY=${MASTER_ENCRYPTION_KEY}
      - ALLOWED_HOSTS=${ALLOWED_HOSTS}
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./ml/models:/app/ml/models:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health/live"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    image: ghcr.io/YOUR_USERNAME/clinomic-frontend:latest
    restart: always
    environment:
      - REACT_APP_BACKEND_URL=${BACKEND_URL}
    depends_on:
      - backend

  nginx:
    image: nginx:alpine
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.prod.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - backend
      - frontend

volumes:
  postgres_data:
EOF

# Testing docker-compose file
cat > $TESTING_DEPLOY_PATH/docker-compose.testing.yml << 'EOF'
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    restart: always
    environment:
      POSTGRES_DB: clinomic_testing
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_testing_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    image: ghcr.io/YOUR_USERNAME/clinomic-backend:latest
    restart: always
    environment:
      - DEBUG=True
      - APP_ENV=testing
      - POSTGRES_HOST=db
      - POSTGRES_PORT=5432
      - POSTGRES_DB=clinomic_testing
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - JWT_REFRESH_SECRET_KEY=${JWT_REFRESH_SECRET_KEY}
      - MASTER_ENCRYPTION_KEY=${MASTER_ENCRYPTION_KEY}
    ports:
      - "8001:8000"
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - ./ml/models:/app/ml/models:ro
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health/live"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    image: ghcr.io/YOUR_USERNAME/clinomic-frontend:latest
    restart: always
    environment:
      - REACT_APP_BACKEND_URL=${BACKEND_URL}
    ports:
      - "3001:3000"
    depends_on:
      - backend

  nginx:
    image: nginx:alpine
    restart: always
    ports:
      - "8080:80"
    volumes:
      - ./nginx.testing.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - backend
      - frontend

volumes:
  postgres_testing_data:
EOF

print_success "Example configuration files created"

# Create placeholder nginx configs
cat > $DEPLOY_PATH/nginx.prod.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:8000;
    }
    
    upstream frontend {
        server frontend:3000;
    }

    # SSL Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";

    server {
        listen 80;
        
        # Redirect all HTTP traffic to HTTPS
        return 301 https://$host$request_uri;
    }
    
    server {
        listen 443 ssl http2;
        
        # SSL certificates
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;
        
        # Logging
        access_log /var/log/nginx/access.log;
        error_log /var/log/nginx/error.log;

        # Client max body size for file uploads
        client_max_body_size 100M;

        # API routes
        location /api/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
            
            # WebSocket support
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
        
        # Admin panel
        location /admin/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
        }
        
        # Static files
        location /static/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # Media files
        location /media/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # Frontend app - serve index.html for all other routes (SPA)
        location / {
            proxy_pass http://frontend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_cache_bypass $http_upgrade;
        }
    }
}
EOF

cat > $TESTING_DEPLOY_PATH/nginx.testing.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:8000;
    }
    
    upstream frontend {
        server frontend:3000;
    }

    # Security headers
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";

    server {
        listen 80;
        
        # Logging
        access_log /var/log/nginx/access.log;
        error_log /var/log/nginx/error.log;

        # Client max body size for file uploads
        client_max_body_size 100M;

        # API routes
        location /api/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
            
            # WebSocket support
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
        
        # Admin panel
        location /admin/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
        }
        
        # Static files
        location /static/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # Media files
        location /media/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # Frontend app - serve index.html for all other routes (SPA)
        location / {
            proxy_pass http://frontend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_cache_bypass $http_upgrade;
        }
    }
}
EOF

print_success "Nginx configuration files created"

# Create a deployment helper script
cat > $DEPLOY_PATH/deploy-helper.sh << 'EOF'
#!/bin/bash
# Deployment helper script

DEPLOY_PATH="/opt/clinomic"
COMPOSE_FILE="$DEPLOY_PATH/docker-compose.prod.yml"

case "$1" in
    "up")
        cd $DEPLOY_PATH
        docker-compose -f $COMPOSE_FILE up -d
        echo "Services started. Waiting for health check..."
        timeout 120 bash -c 'until curl -sf http://localhost:8000/api/health/live; do sleep 2; done' || {
            echo "Health check failed after 120 seconds"
            docker-compose -f $COMPOSE_FILE logs
            exit 1
        }
        echo "Deployment successful!"
        ;;
    "down")
        cd $DEPLOY_PATH
        docker-compose -f $COMPOSE_FILE down
        echo "Services stopped"
        ;;
    "restart")
        cd $DEPLOY_PATH
        docker-compose -f $COMPOSE_FILE restart
        echo "Services restarted"
        ;;
    "logs")
        cd $DEPLOY_PATH
        docker-compose -f $COMPOSE_FILE logs -f
        ;;
    "pull")
        cd $DEPLOY_PATH
        docker-compose -f $COMPOSE_FILE pull
        echo "Images pulled"
        ;;
    *)
        echo "Usage: $0 {up|down|restart|logs|pull}"
        exit 1
        ;;
esac
EOF

chmod +x $DEPLOY_PATH/deploy-helper.sh
chown $DEPLOY_USER:$DEPLOY_USER $DEPLOY_PATH/deploy-helper.sh
print_success "Deployment helper script created"

# Generate SSH key for GitHub Actions (optional)
print_header "GENERATING SSH KEY FOR GITHUB ACTIONS (OPTIONAL)"
if [[ ! -f /home/$DEPLOY_USER/.ssh/deploy_key ]]; then
    ssh-keygen -t ed25519 -C "github-actions-deploy" -f /home/$DEPLOY_USER/.ssh/deploy_key -N ""
    chown $DEPLOY_USER:$DEPLOY_USER /home/$DEPLOY_USER/.ssh/deploy_key*
    
    echo ""
    echo "=========================================="
    echo "ADD THIS PUBLIC KEY TO YOUR REPO SETTINGS:"
    echo "=========================================="
    cat /home/$DEPLOY_USER/.ssh/deploy_key.pub
    echo ""
    echo "=========================================="
    echo "ADD THIS PRIVATE KEY TO GITHUB SECRETS AS 'VPS_SSH_PRIVATE_KEY':"
    echo "=========================================="
    cat /home/$DEPLOY_USER/.ssh/deploy_key
    echo ""
else
    print_warning "SSH key for GitHub Actions already exists"
fi

# Final instructions
print_header "PROVISIONING COMPLETE"
echo ""
echo "The VM has been provisioned successfully!"
echo ""
echo "Next steps:"
echo "1. Add your SSH public key to /home/$DEPLOY_USER/.ssh/authorized_keys"
echo "2. Set up SSL certificates in $SSL_PATH if using HTTPS"
echo "3. Configure your domain DNS to point to this server"
echo "4. Add the GitHub Actions SSH private key to your repo secrets"
echo "5. Set up environment variables in GitHub Actions"
echo ""
echo "For SSL certificates (using Let's Encrypt):"
echo "sudo certbot --nginx -d your-domain.com"
echo ""
echo "To start the application manually:"
echo "sudo -u $DEPLOY_USER docker-compose -f $DEPLOY_PATH/docker-compose.prod.yml up -d"
echo ""
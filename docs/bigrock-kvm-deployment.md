# BigRock KVM Deployment Guide

This document provides specific instructions for deploying the Clinomic B12 Screening Platform on your BigRock KVM server.

## Server Details
- **IP Address**: 66.116.225.67
- **Operating System**: Ubuntu 22.04
- **Hardware**: 4 cores, 8GB RAM, 200GB disk, 3TB bandwidth
- **Duration**: Jan 26, 2026 - Feb 26, 2026
- **Domains**: 
  - Production: clinomiclabs.com
  - Testing: testing.clinomiclabs.com

## Prerequisites Setup

### 1. Server Preparation
Connect to your KVM server via SSH as root and run:

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required software
sudo apt install -y \
    docker.io \
    docker-compose-plugin \
    python3 \
    python3-pip \
    curl \
    git \
    certbot \
    python3-certbot-nginx

# Enable and start Docker
sudo systemctl enable docker
sudo systemctl start docker
```

### 2. Create Deploy User
```bash
# Create deploy user
sudo useradd -m -s /bin/bash deploy

# Add deploy user to docker group
sudo usermod -aG docker deploy

# Create deployment directory
sudo mkdir -p /opt/clinomic
sudo chown deploy:deploy /opt/clinomic

# Set up proper permissions
sudo chmod 755 /opt/clinomic
```

### 3. Network Configuration
```bash
# Configure firewall for medical application security
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 8000/tcp  # Backend API
sudo ufw allow 3000/tcp  # Frontend
sudo ufw --force enable
```

## Application Deployment

### 1. Switch to Deploy User
```bash
sudo su - deploy
cd /opt/clinomic
```

### 2. Clone Repository
```bash
git clone https://github.com/Dev-Abiox/param.git .
```

### 3. Make Scripts Executable
```bash
chmod +x scripts/v3/*.sh
chmod +x scripts/monitoring/*.sh
chmod +x scripts/kvm-deploy.sh
```

### 4. Run Deployment Script
```bash
./scripts/v3/deploy-to-vm.sh
```

This script will:
- Generate secure secrets automatically
- Build Docker images
- Start services in production mode
- Configure monitoring
- Set up auto-start services

## Domain and SSL Configuration

### 1. DNS Setup
Point your domains to the server IP (66.116.225.67):
- clinomiclabs.com → 66.116.225.67
- testing.clinomiclabs.com → 66.116.225.67

### 2. SSL Certificate Setup
```bash
# Get SSL certificates for your domains
sudo certbot certonly --standalone -d clinomiclabs.com -d www.clinomiclabs.com -d testing.clinomiclabs.com

# Create SSL directory for application
sudo mkdir -p /opt/clinomic/ssl

# Copy certificates
sudo cp /etc/letsencrypt/live/clinomiclabs.com/fullchain.pem /opt/clinomic/ssl/
sudo cp /etc/letsencrypt/live/clinomiclabs.com/privkey.pem /opt/clinomic/ssl/
```

### 3. Update Nginx Configuration
Update the nginx configuration to use your domain names:

```bash
# Edit the nginx configuration
sudo nano /opt/clinomic/nginx.prod.conf
```

Replace the server_name directives with your domains:
```
server_name clinomiclabs.com www.clinomiclabs.com;
server_name testing.clinomiclabs.com;
```

## CI/CD Configuration

### GitHub Repository Secrets
Add these secrets to your GitHub repository (Settings > Secrets and Variables > Actions):

#### VM Access Secrets
- `PRODUCTION_VM_HOST` = `66.116.225.67`
- `TESTING_VM_HOST` = `66.116.225.67`
- `VM_USERNAME` = `deploy`
- `VPS_SSH_PRIVATE_KEY` = `[Your SSH private key for deploy user]`

#### Application Secrets
- `POSTGRES_DB` = `clinomic`
- `POSTGRES_USER` = `postgres`
- `POSTGRES_PASSWORD` = `[Secure password]`
- `ALLOWED_HOSTS` = `clinomiclabs.com,www.clinomiclabs.com,testing.clinomiclabs.com,66.116.225.67,localhost`
- `CORS_ORIGINS` = `https://clinomiclabs.com,https://www.clinomiclabs.com,https://testing.clinomiclabs.com,http://66.116.225.67,http://localhost:3000`

### GitHub Environments
Create two environments in your repository:
1. `testing` - for testing deployment
2. `production` - for production deployment

## Medical-Grade Security Configuration

### 1. Data Encryption
The application uses Fernet encryption for PHI data. The deployment script automatically generates the encryption keys.

### 2. Audit Logging
The application implements immutable audit logs with hash chains for compliance.

### 3. Authentication
- JWT tokens with refresh token rotation
- MFA support with TOTP
- Role-based access control

### 4. Security Headers
The nginx configuration includes security headers:
- HSTS (HTTP Strict Transport Security)
- X-Frame-Options
- X-Content-Type-Options
- XSS Protection

## Verification Steps

After deployment, verify the application is working:

```bash
# Check running containers
docker ps

# Check application health
curl http://localhost:8000/api/health/live

# Check logs if needed
./scripts/v3/logs.sh

# Access your applications
# Production: https://clinomiclabs.com
# Testing: https://testing.clinomiclabs.com
```

## Management Commands

```bash
# Start services
./scripts/v3/start.sh prod

# Stop services
./scripts/v3/stop.sh

# View logs
./scripts/v3/logs.sh

# Restart services
./scripts/v3/start.sh prod

# Generate monitoring report
sudo -u deploy /opt/clinomic-monitoring/generate-report.sh
```

## Troubleshooting

### Common Issues

1. **Permission Denied for Docker**:
   ```bash
   sudo usermod -aG docker deploy
   # Logout and login again
   ```

2. **Port Already in Use**:
   ```bash
   # Check what's using the ports
   sudo netstat -tulpn | grep :80
   sudo netstat -tulpn | grep :443
   sudo netstat -tulpn | grep :8000
   ```

3. **Certificate Issues**:
   ```bash
   # Check certificate validity
   sudo certbot certificates
   ```

4. **Database Connection Issues**:
   ```bash
   # Check if database is running
   docker ps | grep postgres
   # Check database logs
   docker logs [db-container-name]
   ```

### Health Checks
```bash
# Backend health
curl -v http://localhost:8000/api/health/live

# Frontend accessibility
curl -v http://localhost:3000
```

## Backup and Recovery

### Database Backup
```bash
# Run the existing backup script
./scripts/backup.sh
```

### Application Backup
Regularly backup:
- SSL certificates: `/opt/clinomic/ssl/`
- Environment file: `/opt/clinomic/.env.v3`
- ML models: `/opt/clinomic/backend_v3/ml/models/`

## Monitoring and Maintenance

### Health Monitoring
The system includes:
- Automated health checks every minute
- Alerting system
- Monitoring dashboard
- Performance metrics

### Updates
- Security patches should be applied regularly
- Docker images can be updated through CI/CD
- Application updates are handled through the pipeline

## Expiration Notice
Your KVM expires on Feb 26, 2026. Plan for either renewal or data migration before that date.

---

For medical-grade compliance, ensure all access is logged and audited, maintain proper backup procedures, and follow your organization's security policies.
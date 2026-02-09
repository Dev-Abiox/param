# Environment Setup Guide

This document outlines the environment variables and secrets required for deploying the Clinomic B12 Screening Platform.

## GitHub Repository Secrets (Minimal)

For security reasons, we now use a secrets-generation approach where sensitive keys are generated on the VM itself. Add only these minimal secrets to your GitHub repository under Settings > Secrets and Variables > Actions:

### VM Access
- `PRODUCTION_VM_HOST` - IP address or domain of production VM
- `TESTING_VM_HOST` - IP address or domain of testing VM  
- `VM_USERNAME` - Username for SSH access (typically "deploy")
- `VPS_SSH_PRIVATE_KEY` - Private SSH key for GitHub Actions to access VMs

### Basic Configuration (Non-sensitive)
- `POSTGRES_DB` - Database name (default: clinomic)
- `POSTGRES_USER` - Database user (default: postgres)
- `POSTGRES_PASSWORD` - PostgreSQL database password (can be set in .env on VM)
- `ALLOWED_HOSTS` - Comma-separated list of allowed hosts (e.g., "yourdomain.com,www.yourdomain.com")
- `CORS_ORIGINS` - Comma-separated list of allowed CORS origins (e.g., "https://yourdomain.com,https://www.yourdomain.com")

## Environments

### Production Environment
Create an environment named `production` with these variables:
- `BACKEND_URL` - Production backend URL (e.g., "https://api.yourdomain.com")
- `FRONTEND_URL` - Production frontend URL (e.g., "https://yourdomain.com")

### Testing Environment
Create an environment named `testing` with these variables:
- `BACKEND_URL` - Testing backend URL (e.g., "https://test-api.yourdomain.com")
- `FRONTEND_URL` - Testing frontend URL (e.g., "https://test.yourdomain.com")

## VM Setup Requirements (Automatic)

The new deployment approach automatically handles secret generation on the VM:

1. Deploy the application code to the VM
2. Run the secrets generation script on the VM
3. The script will automatically generate all required security keys

### On the VM (Production)
1. Create a `deploy` user with Docker access
2. Ensure Docker and Docker Compose are installed
3. Deploy the application code to `/opt/clinomic`
4. Run the secrets generation script: `./scripts/v3/setup-secrets.sh`
5. Run the deployment script: `./scripts/v3/deploy-to-vm.sh`
6. Set up SSL certificates in `/opt/clinomic/ssl/` (if needed)
7. Ensure ports 80, 443, 8000, 3000 are open

### On the VM (Testing)
1. Follow same steps as production but for testing environment

## Secrets Generation on VM

All sensitive keys are now generated automatically on the VM using our setup script:

```bash
# Navigate to the project directory on VM
cd /opt/clinomic

# Run the secrets setup script
./scripts/v3/setup-secrets.sh
```

This script will automatically generate:
- Django Secret Key
- JWT Secret Keys
- Master Encryption Key (for PHI)
- Audit Signing Key

## SSL Certificate Setup (Production)

For production, you'll need to set up SSL certificates. You can use Certbot with Let's Encrypt:

```bash
sudo apt-get update
sudo apt-get install certbot
sudo certbot certonly --standalone -d yourdomain.com
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem /opt/clinomic/ssl/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem /opt/clinomic/ssl/
```

## VM Deployment

To deploy the application to a VM, use the deployment script:

```bash
# On the VM
./scripts/v3/deploy-to-vm.sh
```

This script will:
1. Clone or update the repository
2. Generate secure secrets
3. Build and start the application
4. Configure for production use

## Example .env File for Local Development

```env
# Database
POSTGRES_DB=clinomic
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-db-password
POSTGRES_HOST=localhost
POSTGRES_PORT=5433

# JWT
JWT_SECRET_KEY=your-jwt-secret
JWT_REFRESH_SECRET_KEY=your-refresh-secret

# Encryption
MASTER_ENCRYPTION_KEY=your-fernet-key

# Django
DJANGO_SECRET_KEY=your-django-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```
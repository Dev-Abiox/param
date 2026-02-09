# Environment Setup Guide

This document outlines the environment variables and secrets required for deploying the Clinomic B12 Screening Platform.

## GitHub Repository Secrets

Add these secrets to your GitHub repository under Settings > Secrets and Variables > Actions:

### VM Access
- `PRODUCTION_VM_HOST` - IP address or domain of production VM
- `TESTING_VM_HOST` - IP address or domain of testing VM  
- `VM_USERNAME` - Username for SSH access (typically "deploy")
- `VPS_SSH_PRIVATE_KEY` - Private SSH key for GitHub Actions to access VMs

### Database
- `POSTGRES_PASSWORD` - PostgreSQL database password
- `POSTGRES_DB` - Database name (default: clinomic)
- `POSTGRES_USER` - Database user (default: postgres)

### Security Keys
- `DJANGO_SECRET_KEY` - Django secret key for cryptographic signing
- `JWT_SECRET_KEY` - Secret key for JWT access tokens
- `JWT_REFRESH_SECRET_KEY` - Secret key for JWT refresh tokens
- `MASTER_ENCRYPTION_KEY` - Fernet key for PHI encryption

### Application Settings
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

## VM Setup Requirements

### On the VM (Production)
1. Create a `deploy` user with Docker access
2. Ensure Docker and Docker Compose are installed
3. Create `/opt/clinomic` directory owned by deploy user
4. Set up SSL certificates in `/opt/clinomic/ssl/`
5. Ensure ports 80, 443, 8000, 3000 are open

### On the VM (Testing)
1. Create `/opt/clinomic-testing` directory owned by deploy user
2. Same Docker requirements as production
3. Ensure ports for testing environment are open

## Generating Required Keys

### Django Secret Key
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### JWT Secret Keys
```bash
openssl rand -hex 32
```

### Master Encryption Key (for PHI)
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## SSL Certificate Setup (Production)

For production, you'll need to set up SSL certificates. You can use Certbot with Let's Encrypt:

```bash
sudo apt-get update
sudo apt-get install certbot
sudo certbot certonly --standalone -d yourdomain.com
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem /opt/clinomic/ssl/
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem /opt/clinomic/ssl/
```

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
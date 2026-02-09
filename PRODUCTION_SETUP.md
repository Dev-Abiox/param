# Production CI/CD Pipeline with Blue-Green Deployment

## Overview

This document describes the production CI/CD pipeline for the Clinomic B12 Screening Platform, featuring blue-green deployment for zero-downtime releases on BigRock KVM (66.116.225.67).

## Features

- **Zero-downtime deployments** using blue-green strategy
- **Automated testing** for both frontend and backend
- **Health checks** to ensure service availability
- **Automatic rollback** on deployment failure
- **Minimal GitHub secrets** approach for enhanced security
- **Comprehensive monitoring** and alerting

## GitHub Secrets Required

Only minimal secrets are stored in GitHub for security:

- `SSH_PRIVATE_KEY`: SSH private key for connecting to the VM
- `HOST_IP`: IP address of the BigRock KVM (66.116.225.67)
- `SLACK_WEBHOOK_URL`: (Optional) Slack webhook for notifications

> **Security Note**: All sensitive data (database passwords, API keys, encryption keys) are generated on the VM and never stored in GitHub.

## CI/CD Pipeline Structure

### 1. Test Stage
- **Backend Tests**: Run Python tests with coverage reporting
- **Frontend Tests**: Run JavaScript/React tests with coverage reporting
- Both must pass before proceeding to build stage

### 2. Build Stage
- Builds Docker images for both backend and frontend
- Pushes images to GitHub Container Registry (GHCR)
- Tags images with both `latest` and commit SHA

### 3. Deploy Stage
- Executes blue-green deployment script on the VM
- Supports automatic rollback on failure
- Sends notifications via Slack

## Blue-Green Deployment Process

### Environment Setup
- **Blue Environment**: `/opt/clinomic-b12-platform/blue`
- **Green Environment**: `/opt/clinomic-b12-platform/green`
- **Current Pointer**: `/opt/clinomic-b12-platform/current_env` (contains "blue" or "green")

### Deployment Steps
1. Determines current environment from `current_env` file
2. Deploys to the opposite (next) environment
3. Pulls latest Docker images
4. Starts services in new environment
5. Performs health checks on all services
6. Updates `current_env` to point to new environment
7. Stops old environment services

### Health Checks Performed
- Docker container status
- Backend API health endpoint (`/api/health/`)
- Frontend accessibility (`/`)
- Database connectivity
- System resources (disk, memory)

### Rollback Procedure
- If health checks fail, automatically reverts to previous environment
- Stops failed deployment
- Restarts previous environment
- Updates `current_env` to reflect rollback

## Deployment Scripts

### 1. blue-green-deploy.sh
Main deployment script that handles the complete blue-green process.

### 2. health-check.sh
Monitors the health of deployed services and system resources.

### 3. rollback.sh
Reverts to the previous environment in case of deployment failure.

## Security Approach

### Minimal Secrets Strategy
- SSH key is the only credential stored in GitHub
- All sensitive data generated on VM at runtime
- Encryption keys created dynamically
- Database credentials auto-generated

### Secret Generation
On first deployment, the system generates:
- PostgreSQL password (32-character hex)
- Django secret key (50-character hex)
- Fernet encryption key (properly formatted)
- Stored in `/opt/clinomic-b12-platform/secrets/`

## Architecture Components

### Backend Services
- Django 5.0 REST API with PostgreSQL
- CatBoost ML engine for B12 deficiency classification
- Redis for caching and session storage
- Nginx as reverse proxy

### Frontend Services
- React application with medical-grade UI
- Secure API communication
- Real-time health monitoring

## Accessing the Platform

After successful deployment:
- **Web Interface**: `https://66.116.225.67`
- **API Endpoint**: `https://66.116.225.67/api/`
- **Health Check**: `https://66.116.225.67/api/health/`

## Manual Operations

### Running Health Checks
```bash
sudo /opt/clinomic-b12-platform/scripts/health-check.sh
```

### Manual Rollback
```bash
sudo /opt/clinomic-b12-platform/scripts/rollback.sh
```

### Checking Current Environment
```bash
cat /opt/clinomic-b12-platform/current_env
```

## Troubleshooting

### Common Issues
1. **SSH Connection Failure**: Verify SSH key permissions and host access
2. **Health Check Failures**: Check Docker logs and service status
3. **Database Connection Issues**: Verify PostgreSQL is running and accessible
4. **Resource Exhaustion**: Monitor disk and memory usage

### Diagnostic Commands
```bash
# Check Docker services
docker compose ps

# View logs
docker compose logs

# Check system resources
df -h && free -h
```

## Maintenance

### Regular Tasks
- Monitor deployment logs
- Check health check results
- Review security updates
- Backup critical data

### Log Locations
- Deployment logs: `/opt/clinomic-b12-platform/deployment.log`
- Health check logs: `/opt/clinomic-b12-platform/health-check.log`
- Application logs: Via Docker logs command

---

This production setup ensures reliable, secure, and zero-downtime deployments for the Clinomic B12 Screening Platform on the BigRock KVM infrastructure.
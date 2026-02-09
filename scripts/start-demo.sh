#!/bin/bash
# Clinomic Platform - Quick Start Script
# Usage: ./scripts/start-demo.sh

set -e

echo "========================================"
echo "Clinomic Platform - Demo Startup"
echo "========================================"

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "Error: Docker Compose is not available. Please install Docker Compose."
    exit 1
fi

# Generate secrets if not provided
if [ -z "$JWT_SECRET_KEY" ]; then
    echo "Generating JWT secret key..."
    export JWT_SECRET_KEY=$(openssl rand -base64 64 | tr -d '\n')
fi

if [ -z "$MASTER_ENCRYPTION_KEY" ]; then
    echo "Generating master encryption key..."
    export MASTER_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || openssl rand -base64 32)
fi

if [ -z "$AUDIT_SIGNING_KEY" ]; then
    echo "Generating audit signing key..."
    export AUDIT_SIGNING_KEY=$(openssl rand -hex 64)
fi

# Set demo defaults
export APP_ENV=${APP_ENV:-demo}
export DEMO_MODE_ENABLED=${DEMO_MODE_ENABLED:-true}
export DEMO_USERS_ENABLED=${DEMO_USERS_ENABLED:-true}
export CORS_ORIGINS=${CORS_ORIGINS:-http://localhost:3000}
export REACT_APP_BACKEND_URL=${REACT_APP_BACKEND_URL:-http://localhost:8001}

echo ""
echo "Configuration:"
echo "  APP_ENV: $APP_ENV"
echo "  DEMO_MODE_ENABLED: $DEMO_MODE_ENABLED"
echo "  CORS_ORIGINS: $CORS_ORIGINS"
echo "  REACT_APP_BACKEND_URL: $REACT_APP_BACKEND_URL"
echo ""

# Start services
echo "Starting services with Docker Compose..."
if docker compose version &> /dev/null; then
    docker compose up -d --build
else
    docker-compose up -d --build
fi

echo ""
echo "Waiting for services to be ready..."
sleep 10

# Health check
echo ""
echo "Checking service health..."

BACKEND_HEALTHY=false
for i in {1..30}; do
    if curl -sf http://localhost:8001/api/health/ready > /dev/null 2>&1; then
        BACKEND_HEALTHY=true
        break
    fi
    echo "  Waiting for backend... ($i/30)"
    sleep 2
done

FRONTEND_HEALTHY=false
for i in {1..30}; do
    if curl -sf http://localhost:3000/health > /dev/null 2>&1; then
        FRONTEND_HEALTHY=true
        break
    fi
    echo "  Waiting for frontend... ($i/30)"
    sleep 2
done

echo ""
echo "========================================"
echo "Clinomic Platform Status"
echo "========================================"

if [ "$BACKEND_HEALTHY" = true ]; then
    echo "✅ Backend API:     http://localhost:8001"
else
    echo "❌ Backend API:     Not responding"
fi

if [ "$FRONTEND_HEALTHY" = true ]; then
    echo "✅ Frontend:        http://localhost:3000"
else
    echo "❌ Frontend:        Not responding"
fi

echo ""
echo "Demo Credentials:"
echo "  Admin:   admin / admin"
echo "  Lab:     lab / lab"
echo "  Doctor:  doctor / doctor"
echo ""
echo "API Documentation: http://localhost:8001/docs"
echo ""
echo "To stop: docker-compose down"
echo "To view logs: docker-compose logs -f"
echo "========================================"

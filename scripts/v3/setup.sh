#!/bin/bash
# Initial Setup for Clinomic v3 Platform
# Usage: ./scripts/v3/setup.sh
#
# Sets up the complete v3 environment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "Clinomic Platform v3 - Setup"
echo "=========================================="

# Step 1: Check prerequisites
echo ""
echo "[1/5] Checking prerequisites..."

# Docker
if command -v docker &> /dev/null; then
    echo "  ✓ Docker: $(docker --version | cut -d' ' -f3 | tr -d ',')"
else
    echo "  ✗ Docker: NOT FOUND"
    echo "  Please install Docker from https://www.docker.com/get-started"
    exit 1
fi

# Docker Compose
if docker compose version &> /dev/null; then
    echo "  ✓ Docker Compose: $(docker compose version --short)"
else
    echo "  ✗ Docker Compose: NOT FOUND"
    exit 1
fi

# Step 2: Create .env.v3 file
echo ""
echo "[2/5] Setting up environment file..."

if [ ! -f ".env.v3" ]; then
    if [ -f ".env.v3.example" ]; then
        cp .env.v3.example .env.v3

        # Generate secure keys using Python
        python3 << 'PYTHON'
import secrets
import os

# Generate keys
django_key = secrets.token_urlsafe(50)
jwt_key = secrets.token_urlsafe(32)
refresh_key = secrets.token_urlsafe(32)
audit_key = secrets.token_urlsafe(32)

# Generate Fernet key
try:
    from cryptography.fernet import Fernet
    fernet_key = Fernet.generate_key().decode()
except ImportError:
    fernet_key = "INSTALL_CRYPTOGRAPHY_AND_REGENERATE"

# Read .env.v3
with open('.env.v3', 'r') as f:
    content = f.read()

# Replace empty values
replacements = {
    'DJANGO_SECRET_KEY=\n': f'DJANGO_SECRET_KEY={django_key}\n',
    'JWT_SECRET_KEY=\n': f'JWT_SECRET_KEY={jwt_key}\n',
    'JWT_REFRESH_SECRET_KEY=\n': f'JWT_REFRESH_SECRET_KEY={refresh_key}\n',
    'MASTER_ENCRYPTION_KEY=\n': f'MASTER_ENCRYPTION_KEY={fernet_key}\n',
    'AUDIT_SIGNING_KEY=\n': f'AUDIT_SIGNING_KEY={audit_key}\n',
}

for old, new in replacements.items():
    content = content.replace(old, new)

with open('.env.v3', 'w') as f:
    f.write(content)

print('  ✓ Created .env.v3 with generated keys')
PYTHON
    else
        echo "  ✗ ERROR: .env.v3.example not found"
        exit 1
    fi
else
    echo "  ✓ .env.v3 already exists"
fi

# Step 3: Create ML models directory
echo ""
echo "[3/5] Setting up ML models directory..."

mkdir -p backend_v3/ml/models

if [ "$(ls -A backend_v3/ml/models 2>/dev/null)" ]; then
    echo "  ✓ ML models found"
else
    echo "  ✓ ML models directory created"
    echo "    NOTE: Place model files in backend_v3/ml/models/ for screening to work"
fi

# Step 4: Build Docker images
echo ""
echo "[4/5] Building Docker images..."

docker compose -f docker-compose.v3.yml --profile dev build

echo "  ✓ Docker images built"

# Step 5: Initialize database
echo ""
echo "[5/5] Initializing database..."

# Start database
docker compose -f docker-compose.v3.yml up -d db
echo "  Waiting for database to be ready..."
sleep 5

# Check if database is ready
for i in {1..30}; do
    if docker compose -f docker-compose.v3.yml exec -T db pg_isready -U postgres > /dev/null 2>&1; then
        echo "  ✓ Database is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "  ✗ ERROR: Database failed to start"
        exit 1
    fi
    sleep 1
done

# Run migrations and seed
echo "  Running migrations..."
docker compose -f docker-compose.v3.yml --profile dev run --rm backend_v3_dev python manage.py migrate_schemas --shared

echo "  Seeding demo data..."
docker compose -f docker-compose.v3.yml --profile dev run --rm backend_v3_dev python manage.py seed_demo_data

# Stop services
docker compose -f docker-compose.v3.yml --profile dev down

echo "  ✓ Database initialized"

# Summary
echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "To start the platform:"
echo ""
echo "  ./scripts/v3/start.sh dev"
echo ""
echo "This will start all services:"
echo "  - PostgreSQL (localhost:5433)"
echo "  - Backend API (localhost:8000)"
echo "  - Frontend (localhost:3000)"
echo ""
echo "Demo credentials:"
echo "  admin_demo / Demo@2024"
echo "  lab_demo / Demo@2024"
echo "  doctor_demo / Demo@2024"
echo ""

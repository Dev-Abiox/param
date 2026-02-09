#!/bin/bash
# Initial Setup Script for Clinomic v3
# Usage: ./scripts/setup.sh
#
# This script sets up the development environment from scratch

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=========================================="
echo "Clinomic v3 - Initial Setup"
echo "=========================================="

# Step 1: Python virtual environment
echo ""
echo "[1/7] Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "  Created virtual environment"
else
    echo "  Virtual environment exists"
fi

source venv/bin/activate
echo "  Activated: $VIRTUAL_ENV"

# Step 2: Install dependencies
echo ""
echo "[2/7] Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "  Dependencies installed"

# Step 3: Environment file
echo ""
echo "[3/7] Setting up environment file..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env

        # Generate keys
        DJANGO_KEY=$(python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
        JWT_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
        REFRESH_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
        FERNET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
        AUDIT_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

        # Update .env with generated keys (macOS compatible sed)
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$DJANGO_KEY|" .env
            sed -i '' "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT_KEY|" .env
            sed -i '' "s|JWT_REFRESH_SECRET_KEY=.*|JWT_REFRESH_SECRET_KEY=$REFRESH_KEY|" .env
            sed -i '' "s|MASTER_ENCRYPTION_KEY=.*|MASTER_ENCRYPTION_KEY=$FERNET_KEY|" .env
            sed -i '' "s|AUDIT_SIGNING_KEY=.*|AUDIT_SIGNING_KEY=$AUDIT_KEY|" .env
        else
            sed -i "s|DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$DJANGO_KEY|" .env
            sed -i "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT_KEY|" .env
            sed -i "s|JWT_REFRESH_SECRET_KEY=.*|JWT_REFRESH_SECRET_KEY=$REFRESH_KEY|" .env
            sed -i "s|MASTER_ENCRYPTION_KEY=.*|MASTER_ENCRYPTION_KEY=$FERNET_KEY|" .env
            sed -i "s|AUDIT_SIGNING_KEY=.*|AUDIT_SIGNING_KEY=$AUDIT_KEY|" .env
        fi

        echo "  Created .env with generated keys"
        echo "  IMPORTANT: Update POSTGRES_PASSWORD in .env"
    else
        echo "  ERROR: .env.example not found"
        exit 1
    fi
else
    echo "  .env already exists"
fi

# Load environment
set -a
source .env
set +a

# Step 4: Check PostgreSQL
echo ""
echo "[4/7] Checking PostgreSQL connection..."
DB_HOST=${POSTGRES_HOST:-localhost}
DB_PORT=${POSTGRES_PORT:-5432}
DB_NAME=${POSTGRES_DB:-clinomic}
DB_USER=${POSTGRES_USER:-postgres}

python -c "
import psycopg2
import os
try:
    # Try connecting to postgres database first
    conn = psycopg2.connect(
        host='$DB_HOST',
        port='$DB_PORT',
        dbname='postgres',
        user='$DB_USER',
        password=os.environ.get('POSTGRES_PASSWORD', ''),
    )
    conn.autocommit = True
    cur = conn.cursor()

    # Check if database exists
    cur.execute(\"SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'\")
    if not cur.fetchone():
        print('  Creating database: $DB_NAME')
        cur.execute('CREATE DATABASE $DB_NAME')
    else:
        print('  Database exists: $DB_NAME')

    cur.close()
    conn.close()
    print('  PostgreSQL: OK')
except Exception as e:
    print(f'  PostgreSQL: FAILED')
    print(f'  Error: {e}')
    print('')
    print('  Make sure PostgreSQL is running:')
    print('    brew services start postgresql  # macOS')
    print('    sudo systemctl start postgresql  # Linux')
    exit(1)
"

# Step 5: Run migrations
echo ""
echo "[5/7] Running database migrations..."
python manage.py migrate_schemas --shared
echo "  Migrations applied"

# Step 6: Create ML models directory
echo ""
echo "[6/7] Setting up ML models directory..."
mkdir -p ml/models
if [ "$(ls -A ml/models 2>/dev/null)" ]; then
    echo "  ML models found"
else
    echo "  ML models directory created (place your models here)"
    echo "  WARNING: Screening will not work without ML models"
fi

# Step 7: Seed demo data
echo ""
echo "[7/7] Seeding demo data..."
python manage.py seed_demo_data
echo "  Demo data seeded"

# Summary
echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Update database password in .env if needed:"
echo "   POSTGRES_PASSWORD=your-password"
echo ""
echo "2. Place ML model files in ml/models/:"
echo "   - stage1_model.cbm"
echo "   - stage2_model.cbm"
echo ""
echo "3. Start the development server:"
echo "   ./scripts/start_dev.sh"
echo ""
echo "4. Access the application:"
echo "   http://localhost:8000"
echo ""
echo "Demo credentials:"
echo "   admin_demo / Demo@2024"
echo "   lab_demo / Demo@2024"
echo "   doctor_demo / Demo@2024"
echo ""

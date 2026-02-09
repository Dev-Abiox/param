#!/bin/bash
# Development Server Startup Script for Clinomic v3
# Usage: ./scripts/start_dev.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=========================================="
echo "Clinomic v3 - Development Server"
echo "=========================================="

# Check for virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    if [ -d "venv" ]; then
        echo "Activating virtual environment..."
        source venv/bin/activate
    elif [ -d ".venv" ]; then
        echo "Activating virtual environment..."
        source .venv/bin/activate
    else
        echo "WARNING: No virtual environment found. Consider creating one:"
        echo "  python -m venv venv && source venv/bin/activate"
    fi
fi

# Check for .env file
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "Creating .env from .env.example..."
        cp .env.example .env
        echo "WARNING: Please edit .env with your configuration"
    else
        echo "ERROR: No .env file found. Create one with required variables."
        exit 1
    fi
fi

# Load environment variables
set -a
source .env
set +a

# Set development defaults
export DEBUG=${DEBUG:-True}
export APP_ENV=${APP_ENV:-dev}

# Check database connection
echo ""
echo "Checking database connection..."
python -c "
import psycopg2
import os
try:
    conn = psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST', 'localhost'),
        port=os.environ.get('POSTGRES_PORT', '5432'),
        dbname=os.environ.get('POSTGRES_DB', 'clinomic'),
        user=os.environ.get('POSTGRES_USER', 'postgres'),
        password=os.environ.get('POSTGRES_PASSWORD', ''),
    )
    conn.close()
    print('  Database connection: OK')
except Exception as e:
    print(f'  Database connection: FAILED - {e}')
    print('  Make sure PostgreSQL is running and configured.')
    exit(1)
" || exit 1

# Check if migrations are needed
echo ""
echo "Checking migrations..."
python manage.py showmigrations --plan 2>/dev/null | grep -q "\[ \]" && {
    echo "  Pending migrations found. Running migrations..."
    python manage.py migrate_schemas --shared
} || echo "  All migrations applied."

# Check encryption key
echo ""
echo "Checking encryption..."
python -c "
from apps.core.crypto import is_crypto_ready
if is_crypto_ready():
    print('  Encryption: OK')
else:
    print('  Encryption: NOT CONFIGURED')
    print('  Set MASTER_ENCRYPTION_KEY in .env')
    exit(1)
" || exit 1

# Check ML models
echo ""
echo "Checking ML models..."
if [ -d "ml/models" ] && [ "$(ls -A ml/models 2>/dev/null)" ]; then
    echo "  ML models: Found"
else
    echo "  ML models: NOT FOUND (screening will fail)"
    echo "  Place model files in ml/models/"
fi

echo ""
echo "=========================================="
echo "Starting development server..."
echo "=========================================="
echo ""
echo "Server: http://localhost:8000"
echo "Admin:  http://localhost:8000/admin"
echo "API:    http://localhost:8000/api/"
echo ""
echo "Demo credentials:"
echo "  admin_demo / Demo@2024"
echo "  lab_demo / Demo@2024"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Start the development server
python manage.py runserver 0.0.0.0:8000

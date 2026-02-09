#!/bin/bash
# Production Server Startup Script for Clinomic v3
# Usage: ./scripts/start_prod.sh
#
# Uses Gunicorn with optimal settings for production

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=========================================="
echo "Clinomic v3 - Production Server"
echo "=========================================="

# Check for .env file
if [ ! -f ".env" ]; then
    echo "ERROR: No .env file found. Production requires proper configuration."
    exit 1
fi

# Load environment variables
set -a
source .env
set +a

# Production settings
export DEBUG=False
export APP_ENV=${APP_ENV:-production}

# Validate required environment variables
REQUIRED_VARS=(
    "DJANGO_SECRET_KEY"
    "POSTGRES_PASSWORD"
    "JWT_SECRET_KEY"
    "MASTER_ENCRYPTION_KEY"
)

echo ""
echo "Validating configuration..."
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo "  ERROR: $var is not set"
        exit 1
    fi
    echo "  $var: OK"
done

# Check database connection
echo ""
echo "Checking database..."
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
    print('  Database: OK')
except Exception as e:
    print(f'  Database: FAILED - {e}')
    exit(1)
"

# Run migrations if needed
echo ""
echo "Applying migrations..."
python manage.py migrate_schemas --shared --noinput

# Collect static files
echo ""
echo "Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null || echo "  No static files to collect"

# Gunicorn configuration
WORKERS=${GUNICORN_WORKERS:-4}
THREADS=${GUNICORN_THREADS:-2}
TIMEOUT=${GUNICORN_TIMEOUT:-120}
BIND=${GUNICORN_BIND:-0.0.0.0:8000}

echo ""
echo "=========================================="
echo "Starting Gunicorn..."
echo "=========================================="
echo ""
echo "Workers: $WORKERS"
echo "Threads: $THREADS"
echo "Timeout: $TIMEOUT"
echo "Bind: $BIND"
echo ""

# Start Gunicorn
exec gunicorn clinomic.wsgi:application \
    --bind "$BIND" \
    --workers "$WORKERS" \
    --threads "$THREADS" \
    --timeout "$TIMEOUT" \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    --enable-stdio-inheritance \
    --preload

#!/bin/bash
# Create Django Admin Superuser for Clinomic v3
# Usage: ./scripts/v3/create-admin.sh [username] [password]
#
# Creates a superuser for Django admin panel access

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

USERNAME=${1:-admin}
PASSWORD=${2:-Admin@2024}
EMAIL="${USERNAME}@clinomic.local"

echo "=========================================="
echo "Clinomic v3 - Create Admin User"
echo "=========================================="
echo ""

# Check if backend is running
if ! docker compose -f docker-compose.v3.yml ps backend_v3_dev --format "{{.Status}}" 2>/dev/null | grep -q "Up"; then
    echo "ERROR: Backend service is not running."
    echo "Start it first with: ./scripts/v3/start.sh dev"
    exit 1
fi

# Create superuser
docker compose -f docker-compose.v3.yml exec -T backend_v3_dev python manage.py shell << PYTHON
from apps.core.models import User, Organization

org = Organization.objects.first()
username = "${USERNAME}"
password = "${PASSWORD}"
email = "${EMAIL}"

if User.objects.filter(username=username).exists():
    user = User.objects.get(username=username)
    user.set_password(password)
    user.is_superuser = True
    user.is_staff = True
    user.save()
    print(f"Updated existing user: {username}")
else:
    user = User.objects.create_superuser(
        username=username,
        email=email,
        password=password,
        name="System Admin",
        organization=org
    )
    print(f"Created superuser: {username}")
PYTHON

echo ""
echo "=========================================="
echo "Django Admin Login"
echo "=========================================="
echo ""
echo "  URL:      http://localhost:8000/admin/"
echo "  Username: ${USERNAME}"
echo "  Password: ${PASSWORD}"
echo ""

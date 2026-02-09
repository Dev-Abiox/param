#!/bin/bash
# Start Clinomic v3 Platform (Full Stack)
# Usage: ./scripts/v3/start.sh [dev|prod|db]
#
# Starts PostgreSQL, Backend v3, and Frontend

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

# Default is dev which runs full stack (db + backend + frontend)
MODE=${1:-dev}

echo "=========================================="
echo "Clinomic Platform v3"
echo "Mode: $MODE"
echo "=========================================="

# Check for docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is required but not installed."
    echo "Install Docker from https://www.docker.com/get-started"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "ERROR: Docker daemon is not running."
    echo "Please start Docker and try again."
    exit 1
fi

# Function to display service info
show_service_info() {
    local mode=$1
    echo ""
    echo "=========================================="
    echo "Services Running"
    echo "=========================================="
    echo ""

    # Show running containers
    docker compose -f docker-compose.v3.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true

    echo ""
    echo "=========================================="
    echo "Endpoints"
    echo "=========================================="
    echo ""

    if [ "$mode" = "dev" ]; then
        echo "  Database:"
        echo "    PostgreSQL:     localhost:5433"
        echo "    User:           postgres"
        echo "    Database:       clinomic"
        echo ""
        echo "  Backend API:"
        echo "    Base URL:       http://localhost:8000"
        echo "    Health:         http://localhost:8000/api/health/live"
        echo "    Login:          POST http://localhost:8000/api/auth/login"
        echo "    Admin:          http://localhost:8000/admin/"
        echo ""
        echo "  Frontend:"
        echo "    Web App:        http://localhost:3000"
        echo ""
    elif [ "$mode" = "prod" ]; then
        echo "  Database:"
        echo "    PostgreSQL:     localhost:5433"
        echo ""
        echo "  Backend API:"
        echo "    Base URL:       http://localhost:8000"
        echo "    Health:         http://localhost:8000/api/health/live"
        echo ""
        echo "  Frontend:"
        echo "    Web App:        http://localhost:3000"
        echo ""
    fi

    echo "=========================================="
    echo "Demo Credentials"
    echo "=========================================="
    echo ""
    echo "  Username          Password        Role"
    echo "  ────────────────────────────────────────"
    echo "  admin_demo        Demo@2024       Admin"
    echo "  lab_demo          Demo@2024       Lab Tech"
    echo "  doctor_demo       Demo@2024       Doctor"
    echo ""
    echo "=========================================="
    echo "Commands"
    echo "=========================================="
    echo ""
    echo "  View logs:        ./scripts/v3/logs.sh [service]"
    echo "  Stop all:         ./scripts/v3/stop.sh"
    echo "  Restart:          ./scripts/v3/start.sh $mode"
    echo "  Create admin:     ./scripts/v3/create-admin.sh [user] [pass]"
    echo ""
}

case $MODE in
    dev)
        echo ""
        echo "Starting development environment..."
        echo "(This includes hot-reload for backend and frontend)"
        echo ""

        # Start in detached mode
        docker compose -f docker-compose.v3.yml --profile dev up -d --build

        echo ""
        echo "Waiting for services to be ready..."
        sleep 5

        # Wait for backend to be healthy
        echo "Checking backend health..."
        for i in {1..30}; do
            if curl -s http://localhost:8000/api/health/live > /dev/null 2>&1; then
                echo "Backend is ready!"
                break
            fi
            if [ $i -eq 30 ]; then
                echo "Warning: Backend health check timed out"
            fi
            sleep 2
        done

        show_service_info "dev"

        echo "To view live logs, run: docker compose -f docker-compose.v3.yml logs -f"
        echo ""
        ;;

    prod)
        echo ""
        echo "Starting production environment..."
        echo ""

        docker compose -f docker-compose.v3.yml --profile prod up -d --build

        echo ""
        echo "Waiting for services to be ready..."
        sleep 5

        show_service_info "prod"
        ;;

    db)
        echo ""
        echo "Starting database only..."
        echo ""
        docker compose -f docker-compose.v3.yml up -d db

        echo ""
        echo "Database running at: localhost:5433"
        echo ""
        ;;

    *)
        echo "Usage: $0 [dev|prod|db]"
        echo ""
        echo "Modes:"
        echo "  dev   - Development with hot reload (default)"
        echo "          Includes: PostgreSQL, Backend, Frontend"
        echo ""
        echo "  prod  - Production mode"
        echo "          Includes: PostgreSQL, Backend (gunicorn), Frontend (nginx)"
        echo ""
        echo "  db    - Database only"
        echo "          Includes: PostgreSQL"
        exit 1
        ;;
esac

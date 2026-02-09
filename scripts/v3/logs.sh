#!/bin/bash
# View logs for Clinomic v3 Platform
# Usage: ./scripts/v3/logs.sh [service]
#
# Services: db, backend_v3, backend_v3_dev, frontend, all

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

SERVICE=${1:-all}

case $SERVICE in
    db)
        docker compose -f docker-compose.v3.yml logs -f db
        ;;
    backend|backend_v3)
        docker compose -f docker-compose.v3.yml logs -f backend_v3
        ;;
    dev|backend_v3_dev)
        docker compose -f docker-compose.v3.yml logs -f backend_v3_dev
        ;;
    frontend)
        docker compose -f docker-compose.v3.yml logs -f frontend
        ;;
    all)
        docker compose -f docker-compose.v3.yml logs -f
        ;;
    *)
        echo "Usage: $0 [db|backend|dev|frontend|all]"
        echo ""
        echo "Services:"
        echo "  db       - PostgreSQL database"
        echo "  backend  - Production backend"
        echo "  dev      - Development backend"
        echo "  frontend - Frontend service"
        echo "  all      - All services (default)"
        exit 1
        ;;
esac

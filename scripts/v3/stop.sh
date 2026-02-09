#!/bin/bash
# Stop Clinomic v3 Platform
# Usage: ./scripts/v3/stop.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cd "$PROJECT_ROOT"

echo "=========================================="
echo "Stopping Clinomic Platform v3"
echo "=========================================="

docker compose -f docker-compose.v3.yml --profile dev --profile full down

echo ""
echo "All v3 services stopped."

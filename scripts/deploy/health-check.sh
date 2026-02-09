#!/bin/bash
# ============================================================================
# CLINOMIC HEALTH CHECK SCRIPT
# ============================================================================
# Usage: ./health-check.sh [OPTIONS]
# Options:
#   --url=URL     Health endpoint URL (default: localhost)
#   --timeout=N   Timeout in seconds (default: 30)
#   --verbose     Show detailed output
# ============================================================================

URL="http://localhost:8001/api/health/ready"
TIMEOUT=30
VERBOSE=false

for arg in "$@"; do
    case $arg in
        --url=*)
            URL="${arg#*=}"
            ;;
        --timeout=*)
            TIMEOUT="${arg#*=}"
            ;;
        --verbose)
            VERBOSE=true
            ;;
    esac
done

echo "Health Check: $URL"
echo "Timeout: ${TIMEOUT}s"
echo ""

start_time=$(date +%s)
attempt=1

while true; do
    response=$(curl -sf "$URL" 2>/dev/null)
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo "✓ Health check PASSED (attempt $attempt)"
        if [ "$VERBOSE" = true ]; then
            echo "Response:"
            echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
        fi
        exit 0
    fi
    
    elapsed=$(($(date +%s) - start_time))
    if [ $elapsed -ge $TIMEOUT ]; then
        echo "✗ Health check FAILED after ${TIMEOUT}s ($attempt attempts)"
        exit 1
    fi
    
    if [ "$VERBOSE" = true ]; then
        echo "Attempt $attempt: waiting... (${elapsed}s elapsed)"
    fi
    
    sleep 1
    ((attempt++))
done

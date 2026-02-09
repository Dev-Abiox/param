#!/bin/bash
# ============================================================================
# CLINOMIC APPLICATION HEALTH CHECK SCRIPT
# ============================================================================
# Performs comprehensive health checks on the Clinomic application
# Checks database connectivity, API availability, and service status
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    local status=$1
    local service=$2
    local message=$3
    
    case $status in
        "OK")
            echo -e "${GREEN}✓ $service: $message${NC}"
            ;;
        "WARN")
            echo -e "${YELLOW}⚠ $service: $message${NC}"
            ;;
        "ERROR")
            echo -e "${RED}✗ $service: $message${NC}"
            ;;
        *)
            echo -e "$service: $message"
            ;;
    esac
}

print_header() {
    echo -e "${BLUE}==========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==========================================${NC}"
}

# Configuration
HEALTH_URL=${HEALTH_URL:-"http://localhost:8000/api/health/live"}
READY_URL=${READY_URL:-"http://localhost:8000/api/health/ready"}
BACKEND_URL=${BACKEND_URL:-"http://localhost:8000"}
TIMEOUT=${TIMEOUT:-30}
LOG_FILE=${LOG_FILE:-"/var/log/clinomic-health.log"}

# Function to log health check
log_check() {
    echo "$(date -Iseconds) | $1" >> $LOG_FILE
}

# Function to check if Docker is running
check_docker() {
    if command -v docker &> /dev/null; then
        local version=$(docker --version 2>/dev/null | cut -d' ' -f3)
        print_status "OK" "Docker" "Running ($version)"
        log_check "Docker OK | Version: $version"
        return 0
    else
        print_status "ERROR" "Docker" "Not installed or not in PATH"
        log_check "Docker ERROR | Not available"
        return 1
    fi
}

# Function to check if Docker Compose is running
check_docker_compose() {
    if command -v docker-compose &> /dev/null; then
        local version=$(docker-compose --version 2>/dev/null | cut -d' ' -f4 | tr -d ',')
        print_status "OK" "Docker Compose" "Available ($version)"
        log_check "Docker Compose OK | Version: $version"
        return 0
    else
        print_status "ERROR" "Docker Compose" "Not installed or not in PATH"
        log_check "Docker Compose ERROR | Not available"
        return 1
    fi
}

# Function to check service status
check_service_status() {
    local service_name=$1
    local container_name=$2
    
    if docker ps --format '{{.Names}}' | grep -q "^${container_name}$"; then
        local status=$(docker ps --filter "name=${container_name}" --format '{{.Status}}')
        if [[ $status =~ ^Up.* ]]; then
            print_status "OK" "$service_name" "Running ($status)"
            log_check "$service_name OK | Status: $status"
            return 0
        else
            print_status "ERROR" "$service_name" "Not running ($status)"
            log_check "$service_name ERROR | Status: $status"
            return 1
        fi
    else
        print_status "ERROR" "$service_name" "Container not found"
        log_check "$service_name ERROR | Container not found"
        return 1
    fi
}

# Function to check database connectivity
check_database() {
    local db_container=$(docker ps --format '{{.Names}}' | grep -i db | head -n1)
    
    if [[ -z "$db_container" ]]; then
        print_status "ERROR" "Database" "No database container found"
        log_check "Database ERROR | No container found"
        return 1
    fi
    
    # Test database connectivity
    local db_test_result=$(docker exec $db_container pg_isready -U postgres 2>/dev/null; echo $?)
    
    if [[ $db_test_result -eq 0 ]]; then
        print_status "OK" "Database" "Accessible"
        log_check "Database OK | Container: $db_container"
        return 0
    else
        print_status "ERROR" "Database" "Not accessible"
        log_check "Database ERROR | Container: $db_container"
        return 1
    fi
}

# Function to check API endpoints
check_api_endpoints() {
    local url=$1
    local name=$2
    
    if curl -sf --connect-timeout 5 --max-time $TIMEOUT "$url" > /dev/null 2>&1; then
        local response_time=$(curl -s -o /dev/null -w "%{time_total}" --connect-timeout 5 --max-time $TIMEOUT "$url" 2>/dev/null)
        print_status "OK" "$name" "Responding in ${response_time}s"
        log_check "$name OK | Response time: ${response_time}s"
        return 0
    else
        print_status "ERROR" "$name" "Not responding"
        log_check "$name ERROR | Not responding"
        return 1
    fi
}

# Function to check disk space
check_disk_space() {
    local threshold=${DISK_THRESHOLD:-80}  # Percentage
    local usage=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
    
    if [[ $usage -lt $threshold ]]; then
        print_status "OK" "Disk Space" "Usage: ${usage}%"
        log_check "Disk Space OK | Usage: ${usage}%"
        return 0
    elif [[ $usage -lt 90 ]]; then
        print_status "WARN" "Disk Space" "Usage: ${usage}% (approaching threshold)"
        log_check "Disk Space WARN | Usage: ${usage}%"
        return 0
    else
        print_status "ERROR" "Disk Space" "Usage: ${usage}% (above threshold)"
        log_check "Disk Space ERROR | Usage: ${usage}%"
        return 1
    fi
}

# Function to check memory usage
check_memory() {
    local threshold=${MEM_THRESHOLD:-80}  # Percentage
    local usage=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
    
    if [[ $usage -lt $threshold ]]; then
        print_status "OK" "Memory" "Usage: ${usage}%"
        log_check "Memory OK | Usage: ${usage}%"
        return 0
    elif [[ $usage -lt 90 ]]; then
        print_status "WARN" "Memory" "Usage: ${usage}% (approaching threshold)"
        log_check "Memory WARN | Usage: ${usage}%"
        return 0
    else
        print_status "ERROR" "Memory" "Usage: ${usage}% (above threshold)"
        log_check "Memory ERROR | Usage: ${usage}%"
        return 1
    fi
}

# Function to check application metrics
check_application_metrics() {
    # Check if we can reach the backend and get some basic metrics
    if curl -sf --connect-timeout 5 --max-time $TIMEOUT "$BACKEND_URL/api/health/live" > /dev/null 2>&1; then
        # Try to get some basic metrics
        local uptime=$(curl -s --connect-timeout 5 --max-time 10 "$BACKEND_URL/api/health/live" 2>/dev/null | jq -r '.uptime // empty' 2>/dev/null)
        local timestamp=$(curl -s --connect-timeout 5 --max-time 10 "$BACKEND_URL/api/health/live" 2>/dev/null | jq -r '.timestamp // empty' 2>/dev/null)
        
        if [[ -n "$uptime" ]] || [[ -n "$timestamp" ]]; then
            print_status "OK" "Application Metrics" "Available"
            log_check "Application Metrics OK"
            return 0
        else
            print_status "OK" "Application Metrics" "Basic connectivity OK"
            log_check "Application Metrics OK | Basic connectivity"
            return 0
        fi
    else
        print_status "ERROR" "Application Metrics" "Cannot reach backend"
        log_check "Application Metrics ERROR | Cannot reach backend"
        return 1
    fi
}

# Main health check function
perform_health_check() {
    print_header "CLINOMIC APPLICATION HEALTH CHECK"
    echo "Started: $(date)"
    echo ""
    
    local total_checks=0
    local failed_checks=0
    
    # Check infrastructure
    ((total_checks++))
    if check_docker; then
        ((total_checks++))
        check_docker_compose
    else
        ((failed_checks++))
    fi
    
    # Check disk and memory
    ((total_checks++))
    check_disk_space || ((failed_checks++))
    ((total_checks++))
    check_memory || ((failed_checks++))
    
    # Check services
    ((total_checks++))
    check_service_status "Database" "db" || ((failed_checks++))
    ((total_checks++))
    check_service_status "Backend" "backend" || ((failed_checks++))
    ((total_checks++))
    check_service_status "Frontend" "frontend" || ((failed_checks++))
    ((total_checks++))
    check_service_status "Nginx" "nginx" || ((failed_checks++))
    
    # Check connectivity
    ((total_checks++))
    check_database || ((failed_checks++))
    ((total_checks++))
    check_api_endpoints "$HEALTH_URL" "Live Health Check" || ((failed_checks++))
    ((total_checks++))
    check_api_endpoints "$READY_URL" "Ready Health Check" || ((failed_checks++))
    ((total_checks++))
    check_application_metrics || ((failed_checks++))
    
    # Summary
    echo ""
    print_header "HEALTH CHECK SUMMARY"
    echo "Total checks: $total_checks"
    echo "Failed checks: $failed_checks"
    
    if [[ $failed_checks -eq 0 ]]; then
        print_status "OK" "Overall Status" "All systems operational"
        log_check "HEALTH CHECK SUCCESS | $((total_checks-failed_checks))/$total_checks checks passed"
        return 0
    else
        print_status "ERROR" "Overall Status" "$failed_checks/$total_checks checks failed"
        log_check "HEALTH CHECK FAILED | $((total_checks-failed_checks))/$total_checks checks passed"
        return 1
    fi
}

# Function to send alert (placeholder - integrate with your preferred system)
send_alert() {
    local message=$1
    echo "$(date -Iseconds) ALERT: $message" >> /var/log/clinomic-alerts.log
    
    # Here you could integrate with Slack, email, etc.
    # Example: curl -X POST -H 'Content-type: application/json' --data '{"text":"'"$message"'"}' $SLACK_WEBHOOK_URL
    echo "Alert sent: $message"
}

# Function to run continuous monitoring
run_monitoring() {
    local interval=${MONITOR_INTERVAL:-60}  # seconds
    
    echo "Starting continuous monitoring (interval: $interval seconds)"
    echo "Press Ctrl+C to stop"
    
    while true; do
        if ! perform_health_check > /tmp/health_check_output 2>&1; then
            # Health check failed, send alert
            local failed_message="Health check failed at $(date)"
            cat /tmp/health_check_output >> /tmp/health_check_output
            send_alert "$failed_message"
        fi
        
        sleep $interval
    done
}

# Parse command line arguments
case "${1:-}" in
    "check"|"")
        perform_health_check
        exit $?
        ;;
    "monitor")
        run_monitoring
        ;;
    "status")
        echo "Service Status:"
        docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        ;;
    *)
        echo "Usage: $0 [check|monitor|status]"
        echo "  check   - Perform a one-time health check (default)"
        echo "  monitor - Run continuous monitoring"
        echo "  status  - Show service status"
        exit 1
        ;;
esac
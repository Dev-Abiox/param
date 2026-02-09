#!/bin/bash
# ============================================================================
# CLINOMIC MONITORING DASHBOARD
# ============================================================================
# Provides a real-time dashboard view of the application status
# Shows service status, resource usage, and recent logs
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Configuration
REFRESH_INTERVAL=${DASHBOARD_REFRESH_INTERVAL:-5}  # seconds
LOG_LINES=${DASHBOARD_LOG_LINES:-10}

# Function to clear screen
clear_screen() {
    clear
}

# Function to draw separator
draw_separator() {
    printf '%*s\n' "${COLUMNS:-$(tput cols)}" '' | tr ' ' '='
}

# Function to get system information
get_system_info() {
    echo -e "${CYAN}System Information${NC}"
    draw_separator
    echo -e "Hostname: $(hostname)"
    echo -e "Uptime: $(uptime -p)"
    echo -e "Load Average: $(uptime | awk -F'load average:' '{print $2}')"
    echo -e "Date: $(date)"
    echo ""
}

# Function to get resource usage
get_resource_usage() {
    echo -e "${CYAN}Resource Usage${NC}"
    draw_separator
    
    # Memory usage
    local mem_total=$(free -h | awk 'NR==2{print $2}')
    local mem_used=$(free -h | awk 'NR==2{print $3}')
    local mem_percent=$(free | awk 'NR==2{printf "%.1f%%", $3*100/$2}')
    
    # Disk usage
    local disk_usage=$(df -h / | awk 'NR==2 {print $5}')
    local disk_total=$(df -h / | awk 'NR==2 {print $2}')
    local disk_used=$(df -h / | awk 'NR==2 {print $3}')
    
    # CPU usage
    local cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | awk -F'%' '{print $1"%"}')
    
    echo -e "Memory: $mem_used / $mem_total ($mem_percent used)"
    echo -e "Disk: $disk_used / $disk_total ($disk_usage used)"
    echo -e "CPU: $cpu_usage"
    echo ""
}

# Function to get service status
get_service_status() {
    echo -e "${CYAN}Service Status${NC}"
    draw_separator
    
    local services=("db" "backend" "frontend" "nginx")
    
    for service in "${services[@]}"; do
        local container=$(docker ps --format '{{.Names}}' | grep -i "$service" | head -n1)
        
        if [[ -n "$container" ]]; then
            local status=$(docker ps --filter "name=$container" --format '{{.Status}}')
            local ports=$(docker ps --filter "name=$container" --format '{{.Ports}}')
            
            if [[ $status =~ ^Up.* ]]; then
                echo -e "${GREEN}✓${NC} $container: ${status} | Ports: $ports"
            else
                echo -e "${RED}✗${NC} $container: ${status} | Ports: $ports"
            fi
        else
            echo -e "${RED}✗${NC} $service: Not running"
        fi
    done
    echo ""
}

# Function to get application health
get_app_health() {
    echo -e "${CYAN}Application Health${NC}"
    draw_separator
    
    local health_url="http://localhost:8000/api/health/live"
    local ready_url="http://localhost:8000/api/health/ready"
    
    # Check live health
    if curl -sf --connect-timeout 3 "$health_url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Live Health Check: Operational"
    else
        echo -e "${RED}✗${NC} Live Health Check: Failed"
    fi
    
    # Check ready health
    if curl -sf --connect-timeout 3 "$ready_url" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Ready Health Check: Operational"
    else
        echo -e "${RED}✗${NC} Ready Health Check: Failed"
    fi
    
    # Check response time
    local response_time=$(curl -s -o /dev/null -w "%{time_total}" --connect-timeout 3 --max-time 10 "$health_url" 2>/dev/null || echo "N/A")
    if [[ $response_time != "N/A" ]]; then
        printf "${GREEN}✓${NC} Response Time: %.3fs\n" $response_time
    fi
    
    echo ""
}

# Function to get recent logs
get_recent_logs() {
    echo -e "${CYAN}Recent Logs${NC}"
    draw_separator
    
    # Get logs for each service
    local services=("backend" "frontend" "nginx")
    
    for service in "${services[@]}"; do
        local container=$(docker ps --format '{{.Names}}' | grep -i "$service" | head -n1)
        
        if [[ -n "$container" ]]; then
            echo -e "${PURPLE}$container:${NC}"
            local log_lines=$(docker logs --tail $LOG_LINES $container 2>/dev/null | tail -$LOG_LINES || echo "No recent logs")
            
            if [[ "$log_lines" != "No recent logs" ]]; then
                echo "$log_lines" | while read -r line; do
                    if [[ $line =~ (ERROR|FATAL|CRITICAL) ]]; then
                        echo -e "${RED}$line${NC}"
                    elif [[ $line =~ (WARN|WARNING) ]]; then
                        echo -e "${YELLOW}$line${NC}"
                    else
                        echo "$line"
                    fi
                done
            else
                echo "  No recent logs"
            fi
            echo ""
        fi
    done
}

# Function to get database status
get_db_status() {
    echo -e "${CYAN}Database Status${NC}"
    draw_separator
    
    local db_container=$(docker ps --format '{{.Names}}' | grep -i db | head -n1)
    
    if [[ -n "$db_container" ]]; then
        local db_status=$(docker exec $db_container pg_isready -U postgres 2>/dev/null; echo $?)
        
        if [[ $db_status -eq 0 ]]; then
            echo -e "${GREEN}✓${NC} Database: Connected and accepting connections"
            
            # Get DB stats if possible
            local db_stats=$(docker exec $db_container psql -U postgres -d clinomic -t -c "SELECT COUNT(*) FROM screening_screenings;" 2>/dev/null || echo "N/A")
            if [[ "$db_stats" != "N/A" ]]; then
                echo "Screenings count: $(echo $db_stats | xargs)"
            fi
        else
            echo -e "${RED}✗${NC} Database: Not accessible"
        fi
    else
        echo -e "${RED}✗${NC} Database: Container not found"
    fi
    echo ""
}

# Function to show dashboard
show_dashboard() {
    clear_screen
    
    echo -e "${WHITE}CLINOMIC MONITORING DASHBOARD${NC}"
    draw_separator
    echo ""
    
    get_system_info
    get_resource_usage
    get_service_status
    get_app_health
    get_db_status
    get_recent_logs
    
    echo -e "${YELLOW}Last updated: $(date)${NC}"
    echo -e "${YELLOW}Refresh interval: ${REFRESH_INTERVAL}s (Press Ctrl+C to exit)${NC}"
}

# Main monitoring loop
main() {
    if [[ $# -gt 0 && "$1" == "--once" ]]; then
        show_dashboard
        return 0
    fi
    
    # Check if Docker is available
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed or not in PATH${NC}"
        exit 1
    fi
    
    # Continuous monitoring
    while true; do
        show_dashboard
        sleep $REFRESH_INTERVAL
    done
}

# Run main function
main "$@"
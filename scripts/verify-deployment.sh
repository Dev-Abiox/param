#!/bin/bash

# Production Deployment Verification Script
# Run this after deployment to verify all components are working

set -e

echo "=========================================="
echo "CLINOMIC PRODUCTION VERIFICATION"
echo "=========================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ $1${NC}"
    else
        echo -e "${RED}✗ $1${NC}"
    fi
}

print_check() {
    echo -e "${YELLOW}🔍 Checking: $1${NC}"
}

# 1. Check Docker containers
print_check "Docker container status"
docker-compose -f docker-compose.prod.yml ps
echo ""

# 2. Check backend health
print_check "Backend health endpoint"
if curl -f -H "Host: clinomiclabs.com" http://localhost:8000/api/health/live > /dev/null 2>&1; then
    BACKEND_STATUS=$(curl -s -H "Host: clinomiclabs.com" http://localhost:8000/api/health/live)
    echo -e "${GREEN}✓ Backend healthy: $BACKEND_STATUS${NC}"
else
    echo -e "${RED}✗ Backend health check failed${NC}"
fi
echo ""

# 3. Check frontend
print_check "Frontend availability"
if curl -f http://localhost:3000/ > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Frontend is responding${NC}"
else
    echo -e "${RED}✗ Frontend is not responding${NC}"
fi
echo ""

# 4. Check nginx configuration
print_check "Nginx configuration"
if nginx -t > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Nginx configuration is valid${NC}"
else
    echo -e "${RED}✗ Nginx configuration has errors${NC}"
fi
echo ""

# 5. Check database connectivity
print_check "Database connectivity"
if docker-compose -f docker-compose.prod.yml exec -T db pg_isready -U postgres > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Database is accepting connections${NC}"
else
    echo -e "${RED}✗ Database connectivity issue${NC}"
fi
echo ""

# 6. Check security headers
print_check "Security headers on API endpoints"
SECURITY_HEADERS=$(curl -s -I https://clinomiclabs.com/api/health/live 2>/dev/null | grep -E "(Strict-Transport-Security|X-Frame-Options|X-Content-Type-Options)")
if [ -n "$SECURITY_HEADERS" ]; then
    echo -e "${GREEN}✓ Security headers present${NC}"
    echo "$SECURITY_HEADERS"
else
    echo -e "${YELLOW}⚠ Security headers check inconclusive (may be behind proxy)${NC}"
fi
echo ""

# 7. Check sensitive file blocking
print_check "Sensitive file protection"
SENSITIVE_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" https://clinomiclabs.com/.env 2>/dev/null)
if [ "$SENSITIVE_RESPONSE" = "404" ]; then
    echo -e "${GREEN}✓ Sensitive files are properly blocked${NC}"
else
    echo -e "${RED}✗ Sensitive file protection may not be working (got $SENSITIVE_RESPONSE)${NC}"
fi
echo ""

# 8. Check rate limiting (basic test)
print_check "Rate limiting configuration"
RATE_LIMIT_CONFIG=$(grep -c "limit_req_zone" nginx.prod.conf 2>/dev/null || echo "0")
if [ "$RATE_LIMIT_CONFIG" -gt 0 ]; then
    echo -e "${GREEN}✓ Rate limiting is configured${NC}"
else
    echo -e "${RED}✗ Rate limiting not found in nginx config${NC}"
fi
echo ""

# 9. Check backup script existence
print_check "Backup scripts"
if [ -f "scripts/db-backup.sh" ] && [ -f "scripts/setup-backup-cron.sh" ]; then
    echo -e "${GREEN}✓ Backup scripts are present${NC}"
else
    echo -e "${RED}✗ Backup scripts missing${NC}"
fi
echo ""

# 10. Summary
echo "=========================================="
echo "VERIFICATION SUMMARY"
echo "=========================================="
echo "Run this command to see detailed logs if needed:"
echo "docker-compose -f docker-compose.prod.yml logs --tail=50"
echo ""
echo "To check specific service logs:"
echo "docker-compose -f docker-compose.prod.yml logs [backend|frontend|nginx|db]"
echo ""
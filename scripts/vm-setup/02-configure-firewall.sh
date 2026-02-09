#!/bin/bash
# ============================================================================
# VM Setup Script 2: Configure Firewall (UFW)
# ============================================================================
# Run as root on Ubuntu 22.04 VPS
# ============================================================================

set -e

echo "=========================================="
echo "FIREWALL CONFIGURATION"
echo "=========================================="

# Install UFW if not present
apt-get update
apt-get install -y ufw fail2ban

# Reset UFW
ufw --force reset

# Default policies
ufw default deny incoming
ufw default allow outgoing

# Allow SSH (adjust port if changed)
ufw allow 22/tcp comment 'SSH'

# Allow HTTP/HTTPS
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'

# Allow internal Docker network
ufw allow from 172.28.0.0/16 comment 'Docker internal'

# Enable UFW
ufw --force enable

# Show status
ufw status verbose

echo ""
echo "=========================================="
echo "FAIL2BAN CONFIGURATION"
echo "=========================================="

# Configure Fail2ban
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5
backend = systemd

[sshd]
enabled = true
port = 22
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 86400

[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 3

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
port = http,https
logpath = /var/log/nginx/error.log
maxretry = 10
findtime = 60
EOF

# Restart Fail2ban
systemctl enable fail2ban
systemctl restart fail2ban

# Show status
fail2ban-client status

echo ""
echo "✓ Firewall and Fail2ban configured"
echo ""
echo "Current firewall status:"
ufw status numbered

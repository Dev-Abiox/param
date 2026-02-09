#!/bin/bash
# ============================================================================
# VM Setup Script 1: SSH Hardening
# ============================================================================
# Run as root on Ubuntu 22.04 VPS
# This script hardens SSH to prevent unauthorized access
# ============================================================================

set -e

echo "=========================================="
echo "SSH HARDENING SCRIPT"
echo "=========================================="

# Backup original config
cp /etc/ssh/sshd_config /etc/ssh/sshd_config.backup.$(date +%Y%m%d)

# Create new SSH config
cat > /etc/ssh/sshd_config << 'EOF'
# Clinomic Production SSH Configuration
# Last updated: $(date)

# Network
Port 22
AddressFamily inet
ListenAddress 0.0.0.0

# Authentication
PermitRootLogin prohibit-password
PubkeyAuthentication yes
PasswordAuthentication no
PermitEmptyPasswords no
ChallengeResponseAuthentication no
UsePAM yes

# Security
MaxAuthTries 3
MaxSessions 5
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2

# Disable unused auth methods
HostbasedAuthentication no
IgnoreRhosts yes

# Logging
SyslogFacility AUTH
LogLevel VERBOSE

# Other
X11Forwarding no
PrintMotd no
AcceptEnv LANG LC_*

# SFTP
Subsystem sftp /usr/lib/openssh/sftp-server

# Allow only specific users
AllowUsers root deploy
EOF

# Test config
sshd -t

# Restart SSH
systemctl restart sshd

echo ""
echo "✓ SSH hardening complete"
echo ""
echo "IMPORTANT: Keep your current session open and test SSH in a new terminal!"
echo "Test command: ssh -i your_key deploy@$(curl -s ifconfig.me)"

#!/bin/bash
# ============================================================================
# VM Setup Script 4: Docker Socket Protection
# ============================================================================
# Run as root on Ubuntu 22.04 VPS
# Secures Docker socket access
# ============================================================================

set -e

echo "=========================================="
echo "DOCKER SOCKET PROTECTION"
echo "=========================================="

# Create Docker daemon configuration
mkdir -p /etc/docker

cat > /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "5"
  },
  "live-restore": true,
  "userland-proxy": false,
  "no-new-privileges": true,
  "default-ulimits": {
    "nofile": {
      "Name": "nofile",
      "Hard": 65536,
      "Soft": 65536
    }
  },
  "storage-driver": "overlay2"
}
EOF

# Secure Docker socket permissions
chmod 660 /var/run/docker.sock

# Only docker group can access
chown root:docker /var/run/docker.sock

# Restart Docker
systemctl restart docker

# Verify
docker info | grep -E "Storage Driver|Logging Driver"

echo ""
echo "✓ Docker socket secured"
echo ""
echo "Docker group members:"
getent group docker

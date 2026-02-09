#!/bin/bash
# ============================================================================
# VM Setup Script 3: Create Deploy User
# ============================================================================
# Run as root on Ubuntu 22.04 VPS
# Creates a dedicated deploy user with limited permissions
# ============================================================================

set -e

DEPLOY_USER="deploy"
DEPLOY_PATH="/opt/clinomic"

echo "=========================================="
echo "CREATE DEPLOY USER"
echo "=========================================="

# Create deploy user
if id "$DEPLOY_USER" &>/dev/null; then
    echo "User $DEPLOY_USER already exists"
else
    useradd -m -s /bin/bash $DEPLOY_USER
    echo "Created user: $DEPLOY_USER"
fi

# Create deployment directory
mkdir -p $DEPLOY_PATH
chown -R $DEPLOY_USER:$DEPLOY_USER $DEPLOY_PATH

# Create log directory
mkdir -p /var/log/clinomic
chown -R $DEPLOY_USER:$DEPLOY_USER /var/log/clinomic
touch /var/log/clinomic-deploys.log
chown $DEPLOY_USER:$DEPLOY_USER /var/log/clinomic-deploys.log

# Setup SSH for deploy user
mkdir -p /home/$DEPLOY_USER/.ssh
chmod 700 /home/$DEPLOY_USER/.ssh

# Add GitHub-provided public key (will be provided during setup)
echo "# Add your GitHub Actions deploy key here" > /home/$DEPLOY_USER/.ssh/authorized_keys
chmod 600 /home/$DEPLOY_USER/.ssh/authorized_keys
chown -R $DEPLOY_USER:$DEPLOY_USER /home/$DEPLOY_USER/.ssh

# Add deploy user to docker group
usermod -aG docker $DEPLOY_USER

# Create sudoers entry for specific commands only
cat > /etc/sudoers.d/deploy << 'EOF'
# Deploy user limited sudo access
deploy ALL=(ALL) NOPASSWD: /usr/bin/docker-compose up *
deploy ALL=(ALL) NOPASSWD: /usr/bin/docker-compose down *
deploy ALL=(ALL) NOPASSWD: /usr/bin/docker-compose restart *
deploy ALL=(ALL) NOPASSWD: /usr/bin/docker-compose logs *
deploy ALL=(ALL) NOPASSWD: /usr/sbin/nginx -s reload
deploy ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload nginx
deploy ALL=(ALL) NOPASSWD: /usr/bin/certbot renew *
EOF
chmod 440 /etc/sudoers.d/deploy

echo ""
echo "=========================================="
echo "GENERATE DEPLOY KEY"
echo "=========================================="

# Generate SSH key for GitHub Actions
if [ ! -f /home/$DEPLOY_USER/.ssh/deploy_key ]; then
    ssh-keygen -t ed25519 -C "github-actions-deploy" -f /home/$DEPLOY_USER/.ssh/deploy_key -N ""
    chown $DEPLOY_USER:$DEPLOY_USER /home/$DEPLOY_USER/.ssh/deploy_key*
    
    echo ""
    echo "=========================================="
    echo "ADD THIS PUBLIC KEY TO VM authorized_keys:"
    echo "=========================================="
    cat /home/$DEPLOY_USER/.ssh/deploy_key.pub
    echo ""
    echo "=========================================="
    echo "ADD THIS PRIVATE KEY TO GITHUB SECRETS AS 'VPS_SSH_PRIVATE_KEY':"
    echo "=========================================="
    cat /home/$DEPLOY_USER/.ssh/deploy_key
    echo ""
fi

echo ""
echo "✓ Deploy user created"
echo ""
echo "Next steps:"
echo "1. Copy the public key above to /home/deploy/.ssh/authorized_keys"
echo "2. Add the private key to GitHub Secrets as VPS_SSH_PRIVATE_KEY"
echo "3. Test SSH: ssh -i deploy_key deploy@$(curl -s ifconfig.me)"

#!/bin/bash
# Clinomic Platform - Generate Secure Keys
# Usage: ./scripts/generate-secrets.sh [output_file]

set -e

OUTPUT_FILE=${1:-.env.secrets}

echo "========================================"
echo "Clinomic Platform - Secret Key Generator"
echo "========================================"
echo ""

# Check for required tools
check_openssl() {
    if ! command -v openssl &> /dev/null; then
        echo "Error: openssl is required but not installed."
        exit 1
    fi
}

check_python() {
    if command -v python3 &> /dev/null; then
        PYTHON_CMD=python3
    elif command -v python &> /dev/null; then
        PYTHON_CMD=python
    else
        echo "Warning: Python not found. Using openssl for all keys."
        PYTHON_CMD=""
    fi
}

check_openssl
check_python

echo "Generating secure keys..."
echo ""

# Generate JWT Secret (64 bytes, base64 encoded)
JWT_SECRET=$(openssl rand -base64 64 | tr -d '\n')
echo "✅ JWT_SECRET_KEY generated ($(echo -n $JWT_SECRET | wc -c) chars)"

# Generate Master Encryption Key (Fernet compatible)
if [ -n "$PYTHON_CMD" ]; then
    MASTER_KEY=$($PYTHON_CMD -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || openssl rand -base64 32)
else
    MASTER_KEY=$(openssl rand -base64 32)
fi
echo "✅ MASTER_ENCRYPTION_KEY generated ($(echo -n $MASTER_KEY | wc -c) chars)"

# Generate Audit Signing Key (64 bytes, hex encoded)
AUDIT_KEY=$(openssl rand -hex 64)
echo "✅ AUDIT_SIGNING_KEY generated ($(echo -n $AUDIT_KEY | wc -c) chars)"

# Generate MongoDB credentials for production
MONGO_ROOT_USER="clinomic_admin"
MONGO_ROOT_PASSWORD=$(openssl rand -base64 32 | tr -d '\n' | tr -d '/' | tr -d '+' | head -c 32)
echo "✅ MONGO credentials generated"

echo ""
echo "Writing secrets to: $OUTPUT_FILE"
echo ""

cat > "$OUTPUT_FILE" << EOF
# Clinomic Platform - Secret Keys
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# 
# ⚠️  SECURITY WARNING:
# - Store this file securely
# - Never commit to version control
# - Rotate keys periodically
# - Use secrets manager in production (AWS Secrets Manager, Vault, etc.)

# JWT Authentication
JWT_SECRET_KEY="$JWT_SECRET"

# PHI Encryption (Fernet key)
MASTER_ENCRYPTION_KEY="$MASTER_KEY"

# Audit Log Signing
AUDIT_SIGNING_KEY="$AUDIT_KEY"

# MongoDB Credentials (production)
MONGO_ROOT_USER="$MONGO_ROOT_USER"
MONGO_ROOT_PASSWORD="$MONGO_ROOT_PASSWORD"
EOF

chmod 600 "$OUTPUT_FILE"

echo "✅ Secrets written to $OUTPUT_FILE"
echo ""
echo "========================================"
echo "Next Steps:"
echo "========================================"
echo "1. Review the generated secrets in $OUTPUT_FILE"
echo "2. Add $OUTPUT_FILE to .gitignore"
echo "3. For production, migrate secrets to a secrets manager"
echo "4. Source the file before running: source $OUTPUT_FILE"
echo ""
echo "For production deployment:"
echo "  export \$(cat $OUTPUT_FILE | grep -v '#' | xargs)"
echo "  docker-compose -f docker-compose.prod.yml up -d"
echo "========================================"

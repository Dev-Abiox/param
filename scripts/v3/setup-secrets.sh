#!/bin/bash
# ============================================================================
# CLINOMIC SECRETS SETUP SCRIPT
# ============================================================================
# This script generates secure secrets for the Clinomic application
# and creates the .env.v3 file with appropriate security measures
# ============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}==========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}==========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env.v3"
ENV_EXAMPLE="$PROJECT_ROOT/.env.v3.example"

print_header "CLINOMIC SECRETS SETUP"

echo "This script will:"
echo "1. Generate secure secrets for the application"
echo "2. Create/update the .env.v3 file"
echo "3. Set appropriate permissions for security"
echo ""

read -p "Continue with secrets setup? (yes/no): " confirm
if [[ $confirm != "yes" ]]; then
    echo "Secrets setup cancelled"
    exit 0
fi

# Check if .env.v3.example exists
if [[ ! -f "$ENV_EXAMPLE" ]]; then
    print_error ".env.v3.example not found in $PROJECT_ROOT"
    exit 1
fi

# Copy example file if .env.v3 doesn't exist
if [[ ! -f "$ENV_FILE" ]]; then
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    print_success "Copied .env.v3.example to .env.v3"
fi

# Function to generate secrets
generate_secrets() {
    print_header "GENERATING SECRETS"
    
    # Generate secure keys using Python
    python3 << PYTHON
import secrets
import os
import sys

def generate_secure_keys():
    # Generate keys
    django_key = secrets.token_urlsafe(50)
    jwt_key = secrets.token_urlsafe(32)
    refresh_key = secrets.token_urlsafe(32)
    audit_key = secrets.token_urlsafe(32)
    
    # Generate Fernet key
    try:
        from cryptography.fernet import Fernet
        fernet_key = Fernet.generate_key().decode()
    except ImportError:
        print("Warning: cryptography module not found. Installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "cryptography"])
        from cryptography.fernet import Fernet
        fernet_key = Fernet.generate_key().decode()
    
    # Read .env.v3
    with open('$ENV_FILE', 'r') as f:
        content = f.read()

    # Replace empty values with generated keys
    replacements = {
        'DJANGO_SECRET_KEY=\n': f'DJANGO_SECRET_KEY={django_key}\n',
        'DJANGO_SECRET_KEY=\n': f'DJANGO_SECRET_KEY={django_key}\n',  # Handle if there are multiple occurrences
        'JWT_SECRET_KEY=\n': f'JWT_SECRET_KEY={jwt_key}\n',
        'JWT_REFRESH_SECRET_KEY=\n': f'JWT_REFRESH_SECRET_KEY={refresh_key}\n',
        'MASTER_ENCRYPTION_KEY=\n': f'MASTER_ENCRYPTION_KEY={fernet_key}\n',
        'AUDIT_SIGNING_KEY=\n': f'AUDIT_SIGNING_KEY={audit_key}\n',
    }
    
    # Handle cases where keys have placeholder values
    placeholders = {
        'DJANGO_SECRET_KEY=change-me-in-production\n': f'DJANGO_SECRET_KEY={django_key}\n',
        'JWT_SECRET_KEY=your-jwt-secret\n': f'JWT_SECRET_KEY={jwt_key}\n',
        'JWT_REFRESH_SECRET_KEY=your-refresh-secret\n': f'JWT_REFRESH_SECRET_KEY={refresh_key}\n',
        'MASTER_ENCRYPTION_KEY=your-fernet-key\n': f'MASTER_ENCRYPTION_KEY={fernet_key}\n',
        'AUDIT_SIGNING_KEY=\n': f'AUDIT_SIGNING_KEY={audit_key}\n',
    }
    
    # Apply replacements
    for old, new in replacements.items():
        content = content.replace(old, new)
    
    for old, new in placeholders.items():
        content = content.replace(old, new)
    
    # Write back to file
    with open('$ENV_FILE', 'w') as f:
        f.write(content)
    
    print('  ✓ Generated and updated secrets in .env.v3')

generate_secure_keys()
PYTHON

    if [[ $? -ne 0 ]]; then
        print_error "Failed to generate secrets using Python"
        exit 1
    fi
}

# Set appropriate permissions for the env file
set_permissions() {
    print_header "SETTING FILE PERMISSIONS"
    
    chmod 600 "$ENV_FILE"
    print_success "Set permissions to 600 for .env.v3"
    
    # Verify the file was created properly
    if [[ -f "$ENV_FILE" ]]; then
        print_success ".env.v3 file created successfully"
        print_warning "Ensure .env.v3 is not committed to version control!"
    else
        print_error ".env.v3 file was not created"
        exit 1
    fi
}

# Validate required secrets exist
validate_secrets() {
    print_header "VALIDATING SECRETS"
    
    local missing_secrets=()
    
    # Check for required secrets
    if ! grep -q '^DJANGO_SECRET_KEY=.*[^=]$' "$ENV_FILE"; then
        missing_secrets+=("DJANGO_SECRET_KEY")
    fi
    
    if ! grep -q '^JWT_SECRET_KEY=.*[^=]$' "$ENV_FILE"; then
        missing_secrets+=("JWT_SECRET_KEY")
    fi
    
    if ! grep -q '^JWT_REFRESH_SECRET_KEY=.*[^=]$' "$ENV_FILE"; then
        missing_secrets+=("JWT_REFRESH_SECRET_KEY")
    fi
    
    if ! grep -q '^MASTER_ENCRYPTION_KEY=.*[^=]$' "$ENV_FILE"; then
        missing_secrets+=("MASTER_ENCRYPTION_KEY")
    fi
    
    if [[ ${#missing_secrets[@]} -gt 0 ]]; then
        print_error "Missing required secrets: ${missing_secrets[*]}"
        return 1
    else
        print_success "All required secrets are present"
        return 0
    fi
}

# Create secrets directory for additional security
setup_additional_security() {
    print_header "SETTING UP ADDITIONAL SECURITY"
    
    local secrets_dir="$PROJECT_ROOT/secrets"
    mkdir -p "$secrets_dir"
    
    # Create a script to easily source environment variables
    cat > "$secrets_dir/load-env.sh" << 'EOF'
#!/bin/bash
# Load environment variables from .env.v3
export $(grep -v '^#' .env.v3 | xargs)
EOF
    
    chmod +x "$secrets_dir/load-env.sh"
    print_success "Created secrets directory and load script"
}

# Main execution
main() {
    generate_secrets
    set_permissions
    validate_secrets
    setup_additional_security
    
    print_header "SECRETS SETUP COMPLETE"
    echo ""
    echo "Secrets have been generated and saved to:"
    echo "  $ENV_FILE"
    echo ""
    echo "The following secrets were generated:"
    echo "  - Django Secret Key"
    echo "  - JWT Secret Key"
    echo "  - JWT Refresh Secret Key"
    echo "  - Master Encryption Key (for PHI)"
    echo "  - Audit Signing Key"
    echo ""
    echo "Security measures applied:"
    echo "  - File permissions set to 600 (read/write for owner only)"
    echo "  - Secrets directory created with load script"
    echo ""
    echo "To load environment variables in your session:"
    echo "  source $PROJECT_ROOT/secrets/load-env.sh"
    echo ""
    echo "Remember to never commit the .env.v3 file to version control!"
    echo ""
}

main
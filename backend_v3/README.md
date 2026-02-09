# Clinomic Backend v3

Django + PostgreSQL backend for the Clinomic B12 Screening Platform.

## Tech Stack

- **Framework**: Django 5.0 + Django REST Framework
- **Database**: PostgreSQL 15 with django-tenants (multi-tenant)
- **Authentication**: JWT with refresh token rotation + TOTP MFA
- **Encryption**: Fernet for PHI (patient names)
- **ML**: CatBoost two-stage classifier

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Docker (optional)

### Environment Setup

```bash
# Clone and navigate
cd backend_v3

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
```

### Configure Environment Variables

Edit `.env` with your settings:

```env
# Required
DJANGO_SECRET_KEY=your-secret-key-here
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=clinomic
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-db-password

# JWT (generate secure keys)
JWT_SECRET_KEY=your-jwt-secret
JWT_REFRESH_SECRET_KEY=your-refresh-secret

# PHI Encryption (Fernet key - generate with python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
MASTER_ENCRYPTION_KEY=your-fernet-key
```

### Database Setup

```bash
# Create PostgreSQL database
createdb clinomic

# Run migrations
python manage.py migrate_schemas --shared

# Seed demo data
python manage.py seed_demo_data
```

### Run Development Server

```bash
python manage.py runserver
```

## Docker Setup

Use the project-level docker-compose.v3.yml:

```bash
# From project root
cd ..

# Development (with hot reload)
docker compose -f docker-compose.v3.yml --profile dev up

# Production
docker compose -f docker-compose.v3.yml up backend_v3
```

## Project Structure

```
backend_v3/
├── clinomic/              # Django project settings
│   ├── settings.py        # Configuration
│   ├── urls.py            # URL routing
│   └── wsgi.py            # WSGI entry
├── apps/
│   ├── core/              # Core functionality
│   │   ├── models.py      # User, Organization, MFA, Audit
│   │   ├── authentication.py  # JWT auth
│   │   ├── mfa.py         # TOTP MFA
│   │   ├── crypto.py      # PHI encryption
│   │   └── views.py       # Auth endpoints
│   ├── screening/         # B12 screening
│   │   ├── models.py      # Patient, Lab, Screening
│   │   ├── ml_engine.py   # ML inference
│   │   └── views.py       # Screening endpoints
│   └── analytics/         # Analytics and reporting
├── ml/
│   └── models/            # CatBoost model files
├── scripts/
│   ├── backup.sh          # PostgreSQL backup
│   └── restore.sh         # PostgreSQL restore
└── tests/                 # Test suite
```

## Management Commands

### Seed Demo Data

```bash
# Create demo organization, users, labs, patients
python manage.py seed_demo_data

# Clean and reseed
python manage.py seed_demo_data --clean

# Skip screenings for faster seeding
python manage.py seed_demo_data --skip-screenings
```

Demo credentials:
- Admin: `admin_demo` / `Demo@2024`
- Lab Tech: `lab_demo` / `Demo@2024`
- Doctor: `doctor_demo` / `Demo@2024`

### Migrate from MongoDB (v1)

```bash
# Preview migration
python manage.py migrate_from_mongodb --dry-run

# Full migration
python manage.py migrate_from_mongodb --mongodb-uri "mongodb://localhost:27017/biosaas"

# Migrate specific organization
python manage.py migrate_from_mongodb --org-filter "org-id-here"
```

## API Endpoints

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/login` | POST | Login with username/password |
| `/api/auth/refresh` | POST | Refresh access token |
| `/api/auth/logout` | POST | Revoke refresh token |
| `/api/auth/mfa/setup` | POST | Setup MFA |
| `/api/auth/mfa/verify` | POST | Verify MFA code |

### Screening

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/screening/classify` | POST | Run B12 classification |
| `/api/screening/history` | GET | Get screening history |
| `/api/screening/export` | GET | Export screenings |

### Admin

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/labs` | GET/POST | Lab management |
| `/api/doctors` | GET/POST | Doctor management |
| `/api/patients` | GET/POST | Patient management |
| `/api/audit` | GET | Audit log access |

## Multi-Tenancy

Uses django-tenants for schema-based multi-tenancy:

- Each organization gets isolated PostgreSQL schema
- Shared apps: `core` (users, orgs)
- Tenant apps: `screening`, `analytics`
- Tenant routing via domain or header

## Security Features

- **JWT with Rotation**: Short-lived access tokens, rotating refresh tokens
- **MFA**: TOTP with backup codes
- **PHI Encryption**: Fernet for patient names (fail-closed)
- **Audit Logging**: Immutable hash-chain audit trail
- **Tenant Isolation**: Schema-level data separation
- **Rate Limiting**: Configurable per-endpoint limits

## Backup and Restore

```bash
# Backup
./scripts/backup.sh ./backups

# With S3 upload
S3_BUCKET=my-bucket ./scripts/backup.sh

# Restore
./scripts/restore.sh ./backups/clinomic_20240101_120000.sql.gz
```

## Running Tests

```bash
# Run all tests
pytest

# With coverage
pytest --cov=apps

# Specific test file
pytest tests/test_crypto.py
```

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | Yes | - | Django secret key |
| `DEBUG` | No | False | Debug mode |
| `POSTGRES_HOST` | No | localhost | Database host |
| `POSTGRES_PORT` | No | 5432 | Database port |
| `POSTGRES_DB` | No | clinomic | Database name |
| `POSTGRES_USER` | No | postgres | Database user |
| `POSTGRES_PASSWORD` | Yes | - | Database password |
| `JWT_SECRET_KEY` | Yes | - | JWT signing key |
| `JWT_REFRESH_SECRET_KEY` | Yes | - | Refresh token key |
| `MASTER_ENCRYPTION_KEY` | Yes | - | Fernet PHI encryption key |
| `AUDIT_SIGNING_KEY` | No | - | HMAC key for audit logs |
| `CORS_ORIGINS` | No | - | Allowed CORS origins |

## Migration from v1

1. Ensure MongoDB is accessible
2. Set same `MASTER_ENCRYPTION_KEY` as v1
3. Run migration: `python manage.py migrate_from_mongodb`
4. Verify data: Check counts and sample records
5. Update frontend API URL to point to v3

## License

Proprietary - Clinomic Healthcare Solutions

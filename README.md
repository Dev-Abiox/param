# Clinomic B12 Screening Platform

Cloud-based SaaS for vitamin B12 deficiency screening using machine learning. Built for diagnostic laboratories to automate risk classification from routine CBC blood work.

**Live:** [clinomiclabs.com](https://clinomiclabs.com)

## What It Does

Labs upload CBC (Complete Blood Count) parameters. A two-stage CatBoost ML model classifies patients as normal, borderline, or deficient for B12 — without requiring expensive serum B12 tests. Results are instant, auditable, and available via dashboard or API.

## Architecture

```
                    ┌─────────────┐
                    │   Nginx     │  SSL termination, static files
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │                         │
       ┌──────┴──────┐          ┌──────┴──────┐
       │   React     │          │   Django    │  ASGI (uvicorn)
       │   Frontend  │          │   Backend   │  REST + WebSocket
       └─────────────┘          └──────┬──────┘
                                       │
                    ┌──────────────┬────┴────┬──────────┐
                    │              │         │          │
              ┌─────┴─────┐ ┌─────┴───┐ ┌───┴───┐ ┌───┴────┐
              │ PostgreSQL│ │  Redis  │ │Celery │ │CatBoost│
              │ (tenants) │ │ (cache) │ │(tasks)│ │  (ML)  │
              └───────────┘ └─────────┘ └───────┘ └────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Material-UI, Recharts |
| Backend | Django 5, DRF, Channels (WebSocket) |
| Database | PostgreSQL 15, django-tenants (schema-per-tenant) |
| Auth | JWT with rotation, TOTP MFA, RBAC |
| ML | CatBoost two-stage classifier |
| Queue | Celery + Redis |
| Security | Fernet PHI encryption, HMAC audit chain |
| Infra | Docker, Nginx, GitHub Actions CI/CD |
| Monitoring | Prometheus, Grafana |

## Multi-Tenancy

Each organization (lab) gets an isolated PostgreSQL schema via `django-tenants`. Tenant routing is domain-based. Shared data (users, orgs, billing) lives in the `public` schema; tenant-specific data (patients, screenings, analytics) is isolated per schema.

## Apps

| App | Purpose |
|-----|---------|
| `core` | Authentication, RBAC, users, organizations, MFA, audit logging |
| `screening` | Patient records, CBC data intake, ML classification |
| `analytics` | Dashboards, reports, data export |
| `billing` | Subscription plans, Razorpay integration, usage tracking |

## API Endpoints

### Auth
- `POST /api/auth/login` — Login (returns JWT)
- `POST /api/auth/refresh` — Refresh token
- `POST /api/auth/mfa/setup` — Enable TOTP MFA
- `POST /api/auth/mfa/verify` — Verify MFA code

### Screening
- `POST /api/screening/classify` — Run B12 classification on CBC data
- `GET /api/screening/history` — Screening history
- `GET /api/screening/export` — Export results (CSV/PDF)

### Admin
- `GET/POST /api/labs` — Lab management
- `GET/POST /api/patients` — Patient management
- `GET /api/audit` — Audit trail

### Billing
- `POST /api/billing/signup` — Organization signup with plan selection
- `POST /api/billing/webhook/razorpay` — Payment webhook (HMAC-verified)

### Health
- `GET /api/health/live` — Liveness probe
- `GET /api/health/ready` — Readiness (DB + Redis + ML)

## Development Setup

### Prerequisites

- Python 3.12+, Node 18+, PostgreSQL 15+, Redis 7+

### Backend

```bash
cd backend_v3
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # configure secrets
python manage.py migrate_schemas --shared
python manage.py seed_demo_data
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm ci --legacy-peer-deps
npm start
```

### Docker (Production)

```bash
docker-compose -f docker-compose.prod.yml up -d
```

## CI/CD

GitHub Actions pipelines:

- **`master`** push: test (backend + frontend) → build Docker images → Trivy vulnerability scan → deploy to production
- **`develop`** push: test → build → deploy to testing environment

Both pipelines include automated health checks with rollback on failure.

## Security

- JWT access tokens (15 min) with rotating refresh tokens
- TOTP MFA with encrypted backup codes
- Fernet encryption for all PHI (patient names)
- HMAC SHA-256 hash-chain audit trail (tamper-evident)
- Schema-level tenant isolation
- HSTS, CSP, secure cookies in production
- Startup validation of all critical secrets

## Roles

| Role | Permissions |
|------|------------|
| Super Admin | Platform-wide management, org provisioning |
| Org Admin | Manage labs, users, billing within their org |
| Lab Technician | Submit screenings, view own lab results |
| Doctor | View screenings, access analytics |

## License

Proprietary - Clinomic Healthcare Solutions

# Upgrade Roadmap — Clinomic B12 Screening Platform

**Making Clinomic a Best-in-Class Healthcare SaaS**

**Date:** 2026-02-20

---

## Current State Assessment

Clinomic today is a **strong single-product clinical tool** — it handles B12 screening with a solid ML pipeline, multi-tenancy, HIPAA audit trail, and role-based workflows. However, it is architected as a **monolithic single-server application** with no billing, no self-service tenant onboarding, no real-time features, and limited observability.

To become a **scalable, revenue-generating healthcare SaaS**, the platform needs evolution across seven dimensions:

1. [SaaS Commercialization](#1-saas-commercialization--monetization)
2. [Scaling Architecture](#2-scaling-architecture)
3. [Clinical Intelligence & ML](#3-clinical-intelligence--ml-evolution)
4. [Real-Time & Collaboration](#4-real-time--collaboration)
5. [Compliance & Certifications](#5-compliance--certifications)
6. [Frontend & UX](#6-frontend--ux-modernization)
7. [Developer Experience & Operations](#7-developer-experience--operations)

---

## 1. SaaS Commercialization & Monetization

**Current gap:** No billing, no self-service signup, no usage tracking, no tenant management UI.

### 1.1 Subscription & Billing Engine

```
Priority: HIGH | Effort: 3-4 weeks
```

- **Integrate Razorpay** for subscription management
  - Tier-based pricing already modeled (`Organization.tier`: standard / enterprise / pilot)
  - Map tiers to feature gates and usage limits
  - Razorpay Subscriptions API for recurring billing with plan-based pricing
  - INR-native pricing with multi-currency support for international tenants
- **Usage metering** — Track screenings-per-month per tenant for usage-based pricing
  - Add a `UsageRecord` model: `(organization, month, screening_count, api_calls)`
  - Celery task to compute monthly rollups
- **Invoice generation** — PDF invoices with tenant branding
  - Razorpay auto-generates GST-compliant invoices (critical for Indian market)
- **Payment webhooks** — Handle Razorpay webhook events (subscription cancelled → deactivate tenant)
  - Verify webhook signature using `razorpay.utility.verify_webhook_signature()`
  - Events: `subscription.activated`, `subscription.charged`, `subscription.cancelled`, `payment.failed`

**Pricing model suggestion:**

| Tier | Screenings/month | Features | Price |
|------|-------------------|----------|-------|
| Starter | 500 | Single lab, 3 users, basic analytics | $299/mo |
| Professional | 2,000 | Multi-lab, 10 users, FHIR, bulk import | $799/mo |
| Enterprise | Unlimited | SSO, dedicated support, SLA, custom ML | Custom |

### 1.2 Self-Service Tenant Onboarding

```
Priority: HIGH | Effort: 2-3 weeks
```

- **Sign-up flow** — Organization registration → domain provisioning → admin user creation → schema setup
- **Onboarding wizard** — Guide new admins through: add labs → add doctors → invite users → run first screening
- **Trial period** — 14-day free trial with automatic conversion prompt
- **Auto-provisioning** — `django-tenants` `auto_create_schema = True` is already set; build the API layer on top

### 1.3 Tenant Admin Portal

```
Priority: MEDIUM | Effort: 2 weeks
```

- **User management** — CRUD users within the tenant (currently only via Django admin)
- **Lab & doctor management** — Self-service CRUD (currently seed data only)
- **Usage dashboard** — Show screenings consumed vs. plan limit
- **Billing management** — View invoices, update payment method, upgrade/downgrade plan
- **Branding** — Custom logo and report header per organization

### 1.4 API Key Management

```
Priority: MEDIUM | Effort: 1 week
```

- **API keys for integrations** — Allow tenants to generate API keys for LIS/EHR integrations
- **Scoped permissions** — Read-only keys, screening-only keys, full-access keys
- **Rate limits per key** — Separate from user-based throttling
- **Usage tracking per key** — For billing and auditing

---

## 2. Scaling Architecture

**Current gap:** Single PostgreSQL instance, single Docker host, no horizontal scaling, no connection pooling, synchronous ML inference blocking web workers.

### 2.1 Database Scaling

```
Priority: HIGH | Effort: 2-3 weeks
```

- **Connection pooling with PgBouncer** — The code references PgBouncer in comments (`settings.py:108`) but it's not deployed. Deploy PgBouncer in transaction mode between Django and PostgreSQL.
  - Reduces connection overhead from Gunicorn workers + Celery workers
  - Critical when tenant count grows (each schema multiplies connection demand)

- **Read replicas** — Route analytics queries to a read replica
  - Django database router: `AnalyticsRouter` sends `SummaryView`, `CaseStatsView`, `PatientTrendView` reads to the replica
  - Reduces load on the primary for write-heavy screening operations

- **Partitioning** — Partition the `screenings` table by `created_at` (monthly range partitions)
  - The 7-year retention policy means this table will grow to millions of rows per tenant
  - Partition pruning speeds up time-range queries and makes retention deletion instant (`DROP PARTITION`)

- **Tenant sharding strategy** (future) — As tenant count grows beyond ~100, consider:
  - Shard groups: multiple PostgreSQL clusters, each hosting N tenant schemas
  - Use `django-tenants` custom routing to direct tenants to their shard

### 2.2 Application Scaling

```
Priority: HIGH | Effort: 2-3 weeks
```

- **Container orchestration** — Migrate from single-host Docker Compose to **Kubernetes** (EKS/GKE) or **Docker Swarm**
  - Horizontal Pod Autoscaler for backend workers based on CPU/request latency
  - Separate deployments for: API servers, Celery workers, Celery beat (single replica)
  - Rolling deployments with zero-downtime (already have health checks)

- **Load balancer** — Replace single nginx with AWS ALB / Cloud Load Balancer
  - SSL termination at load balancer level
  - Sticky sessions not needed (stateless JWT auth)
  - Health check integration with `/api/health/ready`

- **ML inference service** — Decouple the ML engine from the Django process
  - Deploy as a separate microservice (FastAPI + uvicorn) with its own scaling
  - Benefits: GPU support, independent scaling, model hot-reload without restarting Django
  - Communication: gRPC or HTTP with circuit breaker pattern
  - Fall back: keep the current in-process engine as a fallback

- **Async screening pipeline** — For high-throughput scenarios:
  ```
  API → Celery task → ML service → store result → notify via WebSocket
  ```
  - `predict_async()` already exists but isn't used — wire it into the view
  - Return a `202 Accepted` with a job ID, let clients poll or receive WebSocket push

### 2.3 Caching Strategy

```
Priority: MEDIUM | Effort: 1 week
```

The current caching is minimal (60s TTL on analytics views). Expand:

- **Model predictions cache** — Cache prediction results keyed on CBC hash (identical inputs = identical outputs)
  - SHA256 of normalized CBC dict → cached result
  - Invalidate when model version changes
  - Avoids redundant ML inference for repeat screenings

- **Tenant-scoped query cache** — Already implemented with `_cache_key()` but only on 3 views
  - Extend to lab/doctor list queries
  - Use cache tags so cache can be invalidated per-tenant when data changes

- **CDN for static assets** — CloudFront / Cloud CDN in front of the frontend build
  - Static assets already have `expires 30d` in nginx; move to a proper CDN

### 2.4 Message Queue & Event-Driven Architecture

```
Priority: MEDIUM | Effort: 3-4 weeks
```

- **Event bus** — Introduce domain events for cross-cutting concerns:
  - `ScreeningCompleted` → trigger notification, update analytics cache, send webhook
  - `HighRiskDetected` → immediate doctor notification, priority queue bump
  - `ConsentRevoked` → flag related screenings, notify lab
  - Start with Django signals; evolve to Redis Streams or RabbitMQ

- **Webhook system** — Allow tenants to register webhook URLs for events:
  - `POST /api/admin/webhooks` — register URLs for event types
  - Celery tasks deliver webhooks with retry + exponential backoff
  - Critical for EHR/LIS integration

---

## 3. Clinical Intelligence & ML Evolution

**Current gap:** Single screening type (B12), static model, no continuous learning, no explainability.

### 3.1 AI-Powered Clinical Decision Support

```
Priority: MEDIUM | Effort: 3-4 weeks
```

- **Template-based clinical narratives** — Generate patient-specific clinical interpretations using a rule-engine and template system (no external API dependency)
  - Build a `NarrativeEngine` with parameterized clinical templates
  - Input: CBC values, risk class, rules fired, patient demographics, historical trend
  - Template logic:
    ```python
    # Example template fragments
    TEMPLATES = {
        "macrocytic_high_risk": "Patient presents with macrocytic anemia (MCV {mcv} fL, ref <100 fL) "
                                "with {hb_status} hemoglobin ({hb} g/dL). Elevated RDW ({rdw}%) suggests "
                                "anisocytosis. {trend_sentence} Clinical pattern is consistent with "
                                "B12 deficiency. Recommend serum B12 and methylmalonic acid confirmation.",
        "borderline_elderly":   "CBC shows borderline macrocytosis (MCV {mcv} fL) in a {age}-year-old "
                                "{sex} patient. {hb_status} hemoglobin ({hb} g/dL) with {rbc_status} RBC. "
                                "Age-adjusted thresholds applied. Consider monitoring with repeat CBC in 3 months.",
    }
    ```
  - Template selection based on: risk class + age group + sex + which clinical rules fired
  - Dynamic sentence fragments for trend analysis ("MCV has increased by {delta} fL over the last {n} screenings")
  - Output rendered alongside the ML classification on the result panel
  - Fully deterministic — same inputs always produce the same narrative (auditable)
  - No network dependency — works offline, zero latency, no API costs
  - Configurable per-tenant (opt-in, with clinical disclaimer)

- **Differential diagnosis suggestions** — When B12 is flagged, suggest related conditions to investigate
  - "Consider: pernicious anemia, celiac disease, Crohn's, metformin-induced B12 depletion"
  - Rule-based lookup table keyed on (risk_class, age_group, fired_rules, CBC_pattern)
  - Ranked by clinical relevance score (hand-tuned by clinical advisors)

### 3.2 Model Lifecycle Management

```
Priority: HIGH | Effort: 2-3 weeks
```

- **Model registry** — Version models with metadata (training date, dataset, metrics, changelog)
  - Store in S3 or a model registry (MLflow, Weights & Biases)
  - The current `version.json` is a good start; formalize it

- **A/B testing** — Run two model versions simultaneously
  - Route 10% of predictions to challenger model
  - Compare performance metrics in production
  - `Screening.model_version` already supports this; add routing logic

- **Model retraining pipeline** —
  - Export anonymized screening outcomes (with doctor review labels) as training data
  - Retrain on accumulated real-world data quarterly
  - Auto-validate against holdout set before promotion

- **Explainability (SHAP/LIME)** —
  - Compute feature importance per prediction
  - Show which CBC parameters most influenced the risk classification
  - Store SHAP values in `Screening.indices` (field already exists)
  - Doctors want to know *why*, not just *what*

### 3.3 Population Health Analytics

```
Priority: MEDIUM | Effort: 3-4 weeks
```

- **Cohort analysis** — B12 deficiency prevalence by age group, sex, lab, region
- **Trend dashboards** — Monthly/quarterly trends across the entire tenant
- **Benchmarking** — Compare a lab's deficiency rate against anonymized platform-wide averages
- **Epidemiological export** — Aggregated, de-identified data export for research purposes
- **Predictive alerts** — "Lab X has a 40% increase in borderline cases this month" → admin notification

---

## 4. Real-Time & Collaboration

**Current gap:** No WebSocket, no real-time notifications, no inter-role collaboration tools.

### 4.1 WebSocket / Server-Sent Events

```
Priority: HIGH | Effort: 2 weeks
```

- **Real-time work queue** — When a lab tech submits a screening, it appears in the work queue instantly for all connected LAB users
  - Django Channels with Redis as the channel layer
  - ASGI server (uvicorn) is already in `requirements.txt`
  - Frontend: native WebSocket or `EventSource` for SSE

- **Live notifications** — Replace polling with push:
  - High-risk screening → doctor gets instant alert
  - Screening reviewed → lab tech sees update
  - Bulk import completed → submitter gets notified

### 4.2 Doctor-Lab Messaging

```
Priority: MEDIUM | Effort: 2-3 weeks
```

- **In-context messaging** — Attach messages to a screening record
  - Doctor can ask lab tech: "Please re-run the RDW on this sample"
  - Lab tech can reply with updated values
  - Message thread linked to `Screening.id`

- **Clinical handoff notes** — Structured handoff between shifts:
  - "3 high-risk cases pending review, 1 requires re-draw"
  - Visible in work queue and doctor dashboard

### 4.3 Mobile-Responsive Design

```
Priority: MEDIUM | Effort: 1-2 weeks
```

- **Mobile-optimized views** — The current UI is desktop-first
  - Doctor dashboard and notification center need mobile-specific layouts
  - Touch-friendly CBC table input
  - Responsive breakpoints for tablet use in lab environments

---

## 5. Compliance & Certifications

**Current gap:** HIPAA foundations are solid (encryption, audit, consent) but no formal certifications or advanced compliance features.

### 5.1 SOC 2 Type II Readiness

```
Priority: HIGH | Effort: 4-6 weeks (process + technical)
```

- **Access reviews** — Automated quarterly access review reports
  - List all users per tenant, their roles, last login
  - Flag dormant accounts (no login in 90 days)

- **Change management** — Enforce PR reviews in CI pipeline
  - Require 1 approving review before merge
  - Branch protection rules on `master`

- **Vulnerability management** —
  - Trivy scanning in CI (container images)
  - Dependabot for Python + npm dependency updates
  - Quarterly penetration testing

- **Incident response** — Documented runbook for data breach scenarios
  - Automated breach notification to affected tenants
  - Audit log export for forensics

### 5.2 HITRUST CSF / ISO 27001

```
Priority: MEDIUM | Effort: Ongoing
```

- Map existing controls to HITRUST CSF framework
- The hash-chain audit log and field-level encryption are strong foundations
- Need: formal risk assessment, vendor management policy, business continuity plan

### 5.3 Regional Compliance

```
Priority: MEDIUM | Effort: 2-3 weeks per region
```

- **GDPR** (EU market expansion):
  - Right to erasure — ability to fully delete a patient's data (currently only retention-based)
  - Data portability — FHIR export of all patient data
  - Data Processing Agreements (DPA) template for tenants
  - Cookie consent (if frontend uses cookies beyond auth)

- **Saudi PDPL / UAE DPL** (regional expansion):
  - Data residency — ensure data stays in-region
  - Arabic-first UI (i18n already supports Arabic)

### 5.4 Clinical Validation & Regulatory

```
Priority: HIGH | Effort: 6-12 months (regulatory process)
```

- **FDA 510(k) / CE marking** — If marketing as a clinical decision support tool
  - The ML model needs formal clinical validation studies
  - Maintain a Design History File (DHF)
  - The existing model reproducibility hashing (`screening_hash`, `model_artifact_hash`) supports this

- **Clinical validation studies** —
  - Prospective study: compare ML predictions against actual serum B12 measurements
  - Publish sensitivity/specificity/PPV/NPV in a peer-reviewed journal
  - This becomes a major competitive differentiator

---

## 6. Frontend & UX Modernization

**Current gap:** Create React App (deprecated), no state management, no lazy loading, no offline support.

### 6.1 Framework Migration

```
Priority: MEDIUM | Effort: 3-4 weeks
```

- **Migrate from CRA to Vite or Next.js**
  - CRA is no longer actively maintained
  - Vite: faster builds, HMR, ESM-native (easiest migration)
  - Next.js: SSR for SEO (landing page), API routes, better code splitting

- **TypeScript migration** — The codebase is pure JavaScript
  - Start with strict mode on new files
  - Gradually convert existing files
  - Type the API service layer first (highest ROI)

### 6.2 State Management

```
Priority: MEDIUM | Effort: 1-2 weeks
```

- **Introduce Zustand or TanStack Query** — Currently all state is local `useState` in components
  - TanStack Query for server state (API caching, revalidation, optimistic updates)
  - Zustand for client state (selected lab, selected doctor, UI preferences)
  - Eliminates prop drilling through `App.js`

### 6.3 Advanced Visualization

```
Priority: MEDIUM | Effort: 2-3 weeks
```

- **Interactive CBC trend charts** — Time-series visualization of patient CBC values over multiple screenings
  - Sparklines in the patient records table
  - Full-page trend view with reference ranges overlaid
  - The backend `PatientTrendView` already provides the data

- **Risk distribution heatmaps** — Geographic or lab-based heatmaps of screening outcomes
- **Model explainability visualization** — SHAP waterfall charts showing feature contributions
- **Printable clinical reports** — PDF generation already exists (`generateReport.js`); enhance with:
  - Trend charts embedded in PDF
  - QR code linking to the digital record
  - Tenant-branded headers and footers

### 6.4 Accessibility (WCAG 2.1 AA)

```
Priority: HIGH | Effort: 2 weeks
```

- **Keyboard navigation** — All interactive elements reachable via Tab
- **Screen reader support** — ARIA labels on all controls
- **Color contrast** — Verify all text meets 4.5:1 contrast ratio
- **Focus management** — Visible focus indicators on all interactive elements
- `eslint-plugin-jsx-a11y` is already installed — enforce its rules strictly

---

## 7. Developer Experience & Operations

### 7.1 Observability Stack

```
Priority: HIGH | Effort: 2-3 weeks
```

- **Metrics** — Prometheus + Grafana
  - Django: request latency (p50/p95/p99), error rate, active connections
  - ML engine: prediction latency, model load time, prediction distribution
  - Celery: task queue depth, processing time, failure rate
  - PostgreSQL: connections, query latency, replication lag
  - Business: screenings/hour, deficiency rate, consent rate

- **Distributed tracing** — OpenTelemetry
  - Trace a screening request from nginx → Django → ML engine → DB → response
  - Identify bottlenecks (is it ML inference or DB queries?)
  - Sentry already has basic tracing (`traces_sample_rate`)

- **Log aggregation** — ELK stack or Grafana Loki
  - structlog JSON output is already production-ready
  - Centralize logs from all containers
  - Alert on error patterns (e.g., CryptoError spike = key rotation issue)

- **Alerting** — PagerDuty / Opsgenie integration
  - P1: ML engine down, DB unreachable, >5% error rate
  - P2: High-risk screening rate spike, Celery queue backing up
  - P3: Certificate expiry warning, disk usage >80%

### 7.2 Infrastructure as Code

```
Priority: MEDIUM | Effort: 2-3 weeks
```

- **Terraform** — Codify all cloud resources
  - VPC, EC2/EKS, RDS, ElastiCache (Redis), S3 buckets, IAM roles
  - Environment parity: dev / staging / production from same modules

- **Helm charts** (if Kubernetes) — Package the application as a Helm chart
  - Values files for each environment
  - Secrets management via AWS Secrets Manager or HashiCorp Vault

### 7.3 CI/CD Evolution

```
Priority: HIGH | Effort: 1-2 weeks
```

- **Pipeline stages:**
  ```
  lint → test → security scan → build → deploy-staging → smoke-test → deploy-prod → canary
  ```

- **Environment promotion:**
  - `develop` branch → auto-deploy to testing
  - `master` branch → deploy to staging → manual approval → deploy to production
  - Blue-green deployment script (`scripts/v3/blue-green-deploy.sh`) already exists — integrate into CI

- **Security scanning:**
  - `trivy` for container image vulnerabilities
  - `bandit` for Python security issues
  - `npm audit` for frontend dependencies
  - `gitleaks` for accidentally committed secrets

- **Database migrations in CI** — Run `migrate_schemas` in a staging DB before production deployment

### 7.4 Developer Onboarding

```
Priority: HIGH | Effort: 1 week
```

- **Docker Compose dev environment** — One-command local setup: `docker compose -f docker-compose.dev.yml up`
  - Hot-reload for both Django and React
  - Pre-seeded database with test data (`seed_demo_data` command exists)
  - ML models included in the dev image

- **Contributing guide** — Branch naming, PR template, code style, test requirements
- **Architecture Decision Records (ADRs)** — Document key decisions:
  - Why schema-per-tenant instead of row-level isolation?
  - Why Fernet instead of AES-GCM?
  - Why CatBoost instead of XGBoost/LightGBM?

---

## 8. Integration Ecosystem

### 8.1 EHR/LIS Integrations

```
Priority: HIGH | Effort: 4-6 weeks
```

- **HL7 v2 interface** — Many labs still use HL7 v2 for LIS communication
  - MLLP listener for inbound ORM/ORU messages
  - Parse OBX segments → extract CBC values → trigger screening
  - Return ORU result message with screening outcome

- **FHIR R4 enhancements** — The current FHIR endpoint accepts bundles; expand:
  - FHIR Subscriptions — push screening results back to EHR
  - SMART on FHIR — launch Clinomic from within an EHR context
  - FHIR operations: `$validate`, `$everything` for patient data export

- **Direct LIS connectors** — Pre-built integrations for major LIS platforms:
  - Sunquest, Cerner PathNet, Epic Beaker
  - Configuration-driven mapping (LOINC code → CBC field)

### 8.2 Third-Party Integrations

```
Priority: MEDIUM | Effort: 1-2 weeks each
```

- **Email (SendGrid/SES)** — Password reset emails, high-risk alerts, scheduled reports
  - Currently password reset tokens are only logged; wire up actual email delivery
- **SMS (Twilio)** — MFA via SMS (alternative to TOTP for less tech-savvy staff)
- **SSO (SAML/OIDC)** — Enterprise customers expect SSO via Azure AD, Okta, Google Workspace
  - Critical for Enterprise tier upsell
- **Slack/Teams** — Bot notifications for high-risk screenings

---

## 9. Implementation Phases

### Phase 1: Foundation (Months 1-2)

Fix the critical bugs from the code review, then lay the SaaS foundation:

1. Fix MFA secret field truncation
2. Fix CaseListView filter ordering
3. Add ConsentRevokeView authorization
4. Remove password reset token from logs
5. Add PgBouncer for connection pooling
6. Set up Prometheus + Grafana monitoring
7. Add Trivy scanning to CI
8. Migrate to Docker Compose V2
9. Create a proper README and contributing guide

### Phase 2: SaaS Engine (Months 2-4)

Turn the product into a revenue-generating SaaS:

1. Razorpay billing integration with tier-based pricing
2. Self-service tenant onboarding flow
3. Tenant admin portal (user/lab/doctor management)
4. API key management for integrations
5. Usage metering and limits
6. Email integration (SendGrid) for transactional emails

### Phase 3: Scale & Intelligence (Months 4-7)

Prepare for growth and differentiate on clinical intelligence:

1. Kubernetes migration (or managed container service)
2. Read replica + PgBouncer optimization
3. WebSocket real-time notifications
4. ML model registry and A/B testing
5. SHAP explainability on predictions
6. Template-based clinical narrative engine (rule-driven, no external API)
7. Differential diagnosis suggestion system

### Phase 4: Enterprise & Compliance (Months 7-10)

Win enterprise customers:

1. SSO (SAML/OIDC) integration
2. SOC 2 Type II audit preparation
3. HL7 v2 interface for LIS integration
4. FHIR Subscription for EHR push
5. Population health analytics dashboard
6. Multi-region deployment (data residency)

### Phase 5: Market Leadership (Months 10-12+)

Establish category leadership:

1. Clinical validation study publication
2. FDA/CE regulatory pathway (if applicable)
3. SMART on FHIR EHR integration
4. Mobile-responsive doctor views
5. Tenant-to-tenant benchmarking analytics
7. Webhook ecosystem for third-party integrations

---

## 10. Competitive Positioning

To become **the best system** in this space, Clinomic should differentiate on:

| Differentiator | Current State | Target State |
|----------------|--------------|--------------|
| **Clinical accuracy** | Single ML model, static | Multi-model A/B testing, continuous learning, published validation |
| **Explainability** | Rule names only | SHAP visualizations, template-driven clinical narratives |
| **Integration** | FHIR Bundle endpoint | HL7 v2, SMART on FHIR, LIS connectors, webhooks |
| **Multi-tenancy** | Schema isolation | Schema isolation + data residency + tenant benchmarking |
| **Compliance** | HIPAA foundations | SOC 2 + HITRUST + clinical validation |
| **Developer experience** | Basic API | OpenAPI docs, SDKs (Python/JS), sandbox environment |
| **Speed to value** | Manual deployment | Self-service signup → first screening in 5 minutes |

The platform's strongest moat will be the **combination of clinical validation + ease of integration + multi-tenant intelligence** — very few competitors can offer all three simultaneously.

---

## 11. Technology Decisions Summary

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| Container orchestration | Kubernetes (EKS) | Auto-scaling, rolling deployments, ecosystem |
| ML serving | Separate FastAPI service | Independent scaling, GPU support, model hot-reload |
| State management (FE) | TanStack Query + Zustand | Server cache + client state, minimal boilerplate |
| Frontend framework | Vite (or Next.js for SSR) | CRA deprecated, 10x faster builds |
| Real-time | Django Channels + Redis | Already have Redis, Channels is Django-native |
| Billing | Razorpay | INR-native, GST-compliant invoices, Subscriptions API |
| SSO | django-allauth + SAML2 | Enterprise requirement, well-maintained |
| Observability | Prometheus + Grafana + Loki | Open source, Kubernetes-native, cost-effective |
| IaC | Terraform | Cloud-agnostic, large ecosystem |
| CI/CD | GitHub Actions (current) | Already working, add stages |
| Clinical narratives | Template engine (built-in) | Zero API cost, deterministic, auditable, offline-capable |

---

*This roadmap should be reviewed quarterly and reprioritized based on customer feedback, revenue data, and competitive landscape.*

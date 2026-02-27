"""
Django settings for Clinomic B12 Screening Platform.

Multi-tenant healthcare SaaS with PostgreSQL, JWT auth, and MFA support.
"""

import os
from datetime import timedelta
from pathlib import Path

import structlog
from dotenv import load_dotenv
from apps.core.config.validation import validate_required_secrets

load_dotenv()

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Security Settings
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
APP_ENV = os.environ.get('APP_ENV', 'dev')

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Multi-Tenant Configuration (django-tenants)
TENANT_MODEL = 'core.Organization'
TENANT_DOMAIN_MODEL = 'core.Domain'

SHARED_APPS = [
    'django_tenants',
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.admin',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party shared
    'rest_framework',
    'corsheaders',
    'django_filters',
    'auditlog',
    'drf_spectacular',
    'channels',
    'django_prometheus',
    # Our shared apps
    'apps.billing',
    'apps.core',
]

TENANT_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    # Apps that have tenant-specific data
    'apps.screening',
    'apps.analytics',
]

INSTALLED_APPS = list(SHARED_APPS) + [
    app for app in TENANT_APPS if app not in SHARED_APPS
]

# Middleware
MIDDLEWARE = [
    'django_prometheus.middleware.PrometheusBeforeMiddleware',  # must be first
    'django_tenants.middleware.main.TenantMainMiddleware',
    'apps.billing.middleware.JWTTenantMiddleware',   # JWT-based tenant override
    'apps.billing.middleware.PlanLimitMiddleware',   # 402 when quota exceeded
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'apps.core.middleware.CorrelationIdMiddleware',   # request_id in every log line
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'auditlog.middleware.AuditlogMiddleware',
    'django_prometheus.middleware.PrometheusAfterMiddleware',   # must be last
]

ROOT_URLCONF = 'clinomic.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'clinomic.wsgi.application'
ASGI_APPLICATION = 'clinomic.asgi.application'

# Database (PostgreSQL with django-tenants)
DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': os.environ.get('POSTGRES_DB', 'clinomic'),
        'USER': os.environ.get('POSTGRES_USER', 'postgres'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', 'postgres'),
        'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        # Keep connections alive for 60 s to avoid reconnect overhead.
        # In production traffic sits behind PgBouncer (transaction mode),
        # so this value applies to the Django ↔ PgBouncer leg only.
        'CONN_MAX_AGE': int(os.environ.get('CONN_MAX_AGE', '60')),
    }
}

DATABASE_ROUTERS = ['django_tenants.routers.TenantSyncRouter']

# Custom User Model
AUTH_USER_MODEL = 'core.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('en', 'English'),
    ('ar', 'Arabic'),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = '/app/staticfiles/'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS Configuration
CORS_ALLOWED_ORIGINS = os.environ.get(
    'CORS_ORIGINS',
    'http://localhost:3000,http://127.0.0.1:3000'
).split(',')
CORS_ALLOW_CREDENTIALS = True

# CSRF trusted origins — required for Django admin POST requests when the
# request comes from a different scheme or subdomain (e.g. https://testing.*)
CSRF_TRUSTED_ORIGINS = os.environ.get(
    'CSRF_TRUSTED_ORIGINS',
    'http://localhost:3000,http://127.0.0.1:3000'
).split(',')

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'apps.core.authentication.JWTAuthentication',
        'apps.core.authentication.APIKeyAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'apps.core.throttling.ResilientAnonRateThrottle',
        'apps.core.throttling.ResilientUserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/minute',
        'user': '100/minute',
        'login': '5/minute',
        'screening': '50/minute',
        'mfa_verify': '5/5minute',  # 5 TOTP attempts per 5-minute window (0.3 / 0.4)
        'mfa_resend': '3/5minute',  # 3 OTP resends per 5-minute window
    },
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# ── OpenAPI / Spectacular ──────────────────────────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'Clinomic B12 Screening API',
    'DESCRIPTION': (
        'Multi-tenant healthcare SaaS — B12 deficiency screening, '
        'CBC analysis, LAB work queue, and doctor review workflow.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SERVERS': [
        {'url': '/api/v1', 'description': 'Current'},
        {'url': '/api', 'description': 'Legacy (deprecated)'},
    ],
    # Security scheme for JWT Bearer tokens
    'SECURITY': [{'BearerAuth': []}],
    'COMPONENT_SECURITY_SCHEMES': {
        'BearerAuth': {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
        }
    },
    'TAGS': [
        {'name': 'auth', 'description': 'Authentication & MFA'},
        {'name': 'screening', 'description': 'B12 Screening & CBC Prediction'},
        {'name': 'analytics', 'description': 'Dashboard & Reporting'},
        {'name': 'admin', 'description': 'Admin-only operations'},
    ],
}

# JWT Settings
JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY', SECRET_KEY)

# Razorpay billing
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')
RAZORPAY_WEBHOOK_SECRET = os.environ.get('RAZORPAY_WEBHOOK_SECRET', '')
BASE_DOMAIN = os.environ.get('BASE_DOMAIN', 'clinomiclabs.com')
JWT_ALGORITHM = 'HS256'
JWT_ACCESS_TOKEN_LIFETIME = timedelta(minutes=int(os.environ.get('ACCESS_TOKEN_EXPIRE_MINUTES', '60')))
JWT_REFRESH_TOKEN_LIFETIME = timedelta(days=int(os.environ.get('REFRESH_TOKEN_EXPIRE_DAYS', '30')))

# MFA Settings
MFA_REQUIRED_ROLES = os.environ.get('MFA_REQUIRED_ROLES', 'LAB,DOCTOR').split(',')
MFA_ISSUER_NAME = 'Clinomic'

# PHI Encryption
MASTER_ENCRYPTION_KEY = os.environ.get('MASTER_ENCRYPTION_KEY', '')

# Audit Settings
AUDIT_SIGNING_KEY = os.environ.get('AUDIT_SIGNING_KEY', '')
AUDITLOG_INCLUDE_ALL_MODELS = True

# Email (SMTP for password reset)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend' if APP_ENV in ('production', 'prod', 'staging', 'testing') else 'django.core.mail.backends.console.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', f'Clinomic <{EMAIL_HOST_USER}>' if EMAIL_HOST_USER else 'Clinomic <noreply@clinomiclabs.com>')
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

# ML Engine Settings
ML_MODEL_DIR = BASE_DIR / 'ml' / 'models'
ML_EXECUTOR_WORKERS = int(os.environ.get('ML_EXECUTOR_WORKERS', '4'))

# Security Headers (production)
if APP_ENV in ('production', 'prod'):
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ── Cache (Redis) ──────────────────────────────────────────────────────────────
# Use CACHE_REDIS_URL (DB 1) separately from REDIS_URL (DB 0, Celery broker) to
# prevent cache key collisions with Celery task metadata in Celery worker processes.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('CACHE_REDIS_URL', 'redis://redis:6379/1'),
    }
}

# ── Channels (WebSocket) ─────────────────────────────────────────────────────
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [os.environ.get('CHANNELS_REDIS_URL', 'redis://redis:6379/2')],
            'prefix': 'ws',
        },
    },
}

# ── Celery ────────────────────────────────────────────────────────────────────
from celery.schedules import crontab  # noqa: E402

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', os.environ.get('REDIS_URL', 'redis://redis:6379/0'))
CELERY_RESULT_BACKEND = os.environ.get('CELERY_BROKER_URL', os.environ.get('REDIS_URL', 'redis://redis:6379/0'))
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_RESULT_SERIALIZER = 'json'

# H1: Reliability — acks_late + reject_on_lost ensure tasks are not dropped
# if the worker crashes mid-execution (message stays in broker until acked).
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# Route tasks into purpose-specific queues so a slow webhook doesn't starve
# the alert queue. Workers consume all queues: -Q default,webhooks,alerts,email
CELERY_TASK_ROUTES = {
    'billing.deliver_webhook':       {'queue': 'webhooks'},
    'billing.send_high_risk_alert':  {'queue': 'alerts'},
    'billing.send_usage_alert':      {'queue': 'email'},
    'billing.send_lab_created_email': {'queue': 'email'},
    'billing.send_welcome_email':    {'queue': 'email'},
    'billing.send_mfa_otp_email':    {'queue': 'email'},
}

# Dead-letter: after max_retries are exhausted Celery marks the task FAILURE.
# A separate Celery Beat job can sweep failed tasks; for now we log via Sentry.
CELERY_TASK_STORE_ERRORS_EVEN_IF_IGNORED = True

# Data Retention Policy (HIPAA §164.530(j) — minimum 6 years; default 7)
DATA_RETENTION_DAYS = int(os.environ.get('DATA_RETENTION_DAYS', '2555'))

CELERY_BEAT_SCHEDULE = {
    # Hourly: clean up expired JWT refresh tokens
    'purge-expired-refresh-tokens': {
        'task': 'core.purge_expired_refresh_tokens',
        'schedule': 3600,   # seconds
    },
    # Hourly: transition active consents whose expires_at has passed
    'expire-stale-consents': {
        'task': 'core.expire_stale_consents',
        'schedule': 3600,   # seconds
    },
    # Daily 02:00 UTC: enforce screening & consent retention policy
    'purge-old-screenings': {
        'task': 'core.purge_old_screenings',
        'schedule': crontab(hour=2, minute=0),
    },
    'purge-old-consents': {
        'task': 'core.purge_old_consents',
        'schedule': crontab(hour=2, minute=5),
    },
    # Daily 03:00 UTC: pg_dump → gzip → S3 (no-op when BACKUP_S3_BUCKET unset)
    'backup-database': {
        'task': 'core.backup_database',
        'schedule': crontab(hour=3, minute=0),
    },
    # Monthly 00:05 UTC on the 1st: archive usage records + reset counters
    'compute-monthly-usage-rollups': {
        'task': 'billing.compute_monthly_rollups',
        'schedule': crontab(hour=0, minute=5, day_of_month=1),
    },
}

# ── Startup secret validation (must run after all secrets are read) ──────────
validate_required_secrets(
    APP_ENV, SECRET_KEY, MASTER_ENCRYPTION_KEY, AUDIT_SIGNING_KEY,
    razorpay_key_id=RAZORPAY_KEY_ID,
    razorpay_key_secret=RAZORPAY_KEY_SECRET,
    razorpay_webhook_secret=RAZORPAY_WEBHOOK_SECRET,
    email_host_user=EMAIL_HOST_USER,
    email_host_password=EMAIL_HOST_PASSWORD,
)

# Logging (stdlib — structlog renders through this handler)
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

# ── Structlog ──────────────────────────────────────────────────────────────────
# Production → JSON (machine-readable, ships well to log aggregators).
# Development → ConsoleRenderer (human-readable, coloured).
_shared_processors = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
]

if APP_ENV in ('production', 'prod'):
    _renderer = structlog.processors.JSONRenderer()
else:
    _renderer = structlog.dev.ConsoleRenderer()

structlog.configure(
    processors=_shared_processors + [
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

# ── Sentry (optional — only initialised when SENTRY_DSN is set) ───────────────
SENTRY_DSN = os.environ.get('SENTRY_DSN', '')

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration(), RedisIntegration()],
        traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
        send_default_pii=False,   # Never send PII/PHI to Sentry
        environment=APP_ENV,
    )

# ── S3 Backup (optional — only active when BACKUP_S3_BUCKET is set) ───────────
BACKUP_S3_BUCKET = os.environ.get('BACKUP_S3_BUCKET', '')
BACKUP_S3_PREFIX = os.environ.get('BACKUP_S3_PREFIX', 'db-backups/')
AWS_BACKUP_ACCESS_KEY_ID = os.environ.get('AWS_BACKUP_ACCESS_KEY_ID', '')
AWS_BACKUP_SECRET_ACCESS_KEY = os.environ.get('AWS_BACKUP_SECRET_ACCESS_KEY', '')

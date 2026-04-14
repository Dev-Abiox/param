"""
Custom Prometheus metrics for the business-critical hot paths.

django_prometheus already emits per-URL-pattern HTTP counters and
latency histograms via middleware. That's enough to see traffic
shape, but it can't answer the questions ops actually asks during
an incident:

    - "Is the ML model slow or is it the DB?" — predict latency split
      from HTTP latency.
    - "Are we losing money right now?" — webhook failure rate by
      event type.
    - "Is somebody brute-forcing a login?" — login outcomes grouped
      by reason.

These counters and histograms are deliberately narrow: labels are
only dimensions ops needs to filter on at query time. No per-user,
per-org, or per-IP labels — those are Sentry / audit log territory,
not Prometheus. Keeping cardinality low so /metrics scrapes stay fast.

All metric names are prefixed `clinomic_` so they can't collide with
django_prometheus or the runtime-provided collectors.

Import from anywhere: `from apps.core.metrics import SCREENING_PREDICT_LATENCY`.

If prometheus_client isn't installed (e.g. a slim dev environment),
every metric degrades to a no-op shim so the import always works.
"""

try:
    from prometheus_client import Counter, Histogram
    _PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover — prod always has it
    _PROMETHEUS_AVAILABLE = False


class _NoopMetric:
    """Stand-in used when prometheus_client isn't importable."""

    def labels(self, *args, **kwargs):
        return self

    def inc(self, *args, **kwargs):
        pass

    def observe(self, *args, **kwargs):
        pass

    def time(self):
        class _Ctx:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

        return _Ctx()


def _counter(name, description, labelnames=()):
    if _PROMETHEUS_AVAILABLE:
        return Counter(name, description, labelnames)
    return _NoopMetric()


def _histogram(name, description, labelnames=(), buckets=None):
    if _PROMETHEUS_AVAILABLE:
        if buckets is not None:
            return Histogram(name, description, labelnames, buckets=buckets)
        return Histogram(name, description, labelnames)
    return _NoopMetric()


# ── Screening prediction ──────────────────────────────────────────────────────
# Latency buckets tuned for the CatBoost two-stage classifier: sub-200ms
# is "happy", 200-1000ms is "warming" or under load, >1s is "degraded".
SCREENING_PREDICT_LATENCY = _histogram(
    'clinomic_screening_predict_seconds',
    'End-to-end latency of POST /api/screening/predict, in seconds.',
    labelnames=('outcome',),  # 'ok' | 'ml_not_ready' | 'error' | 'idempotent'
    buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0),
)

# Distribution of predicted risk classes. Sudden shifts in this ratio
# are the earliest signal of ML drift.
SCREENING_PREDICT_OUTCOMES = _counter(
    'clinomic_screening_predict_outcomes_total',
    'Count of screening predictions by risk class.',
    labelnames=('risk_class',),  # 1 (normal) | 2 (borderline) | 3 (deficient)
)


# ── Billing webhook ───────────────────────────────────────────────────────────
BILLING_WEBHOOK_EVENTS = _counter(
    'clinomic_billing_webhook_events_total',
    'Razorpay webhooks received, grouped by event type and outcome.',
    labelnames=('event_type', 'outcome'),  # outcome: accepted|duplicate|invalid_signature|lock_contended|error|forbidden_ip|unconfigured
)

BILLING_WEBHOOK_LATENCY = _histogram(
    'clinomic_billing_webhook_seconds',
    'End-to-end latency of POST /api/billing/webhook/, in seconds.',
    labelnames=('event_type',),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


# ── Auth ──────────────────────────────────────────────────────────────────────
AUTH_LOGIN_OUTCOMES = _counter(
    'clinomic_auth_login_outcomes_total',
    'POST /api/auth/login results by outcome.',
    # outcome values (rough taxonomy — emitter side keeps this stable):
    #   success               — access token issued, no MFA step required
    #   mfa_required          — password OK, OTP challenge issued
    #   mfa_setup_required    — password OK, user must enroll in MFA first
    #   trusted_device_skip   — MFA skipped because of a valid device cookie
    #   bad_credentials       — wrong username or password
    #   account_inactive      — user exists but is deactivated
    #   rate_limited          — blocked by throttle
    labelnames=('outcome',),
)

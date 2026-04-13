#!/usr/bin/env bash
#
# Razorpay live-mode go-live verification.
#
# Runs all the safety checks needed before announcing payments are live.
# Safe to run repeatedly — read-only.
#
# Usage (on production server):
#   cd /opt/clinomic-b12-platform
#   bash /opt/clinomic-b12-platform/verify-razorpay-live.sh
#
# Or one-shot from your laptop:
#   ssh deploy@<server> 'bash -s' < scripts/verify-razorpay-live.sh

set -u  # error on unset vars but DO NOT exit on errors — we want to run all checks

GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[0;33m"
BLUE="\033[0;34m"
RESET="\033[0m"

PASS=0
FAIL=0
WARN=0

ok()    { echo -e "${GREEN}✓${RESET} $1"; PASS=$((PASS+1)); }
fail()  { echo -e "${RED}✗${RESET} $1"; FAIL=$((FAIL+1)); }
warn()  { echo -e "${YELLOW}⚠${RESET} $1"; WARN=$((WARN+1)); }
info()  { echo -e "${BLUE}i${RESET} $1"; }

echo
echo "=========================================="
echo "  Razorpay Live-Mode Verification"
echo "=========================================="
echo

# ── 1. Find backend container ──────────────────────────────────────────────
BACKEND_CTR=$(docker ps -qf name=backend | head -1)
if [ -z "$BACKEND_CTR" ]; then
    fail "No running backend container found"
    echo
    echo "Run: docker-compose -f /opt/clinomic-b12-platform/docker-compose.prod.yml up -d"
    exit 1
fi
ok "Backend container running: $BACKEND_CTR"

# ── 2. Verify Razorpay API key is LIVE (not test) ──────────────────────────
KEY_PREFIX=$(docker exec "$BACKEND_CTR" python -c \
    "from django.conf import settings; print(settings.RAZORPAY_KEY_ID[:8] if settings.RAZORPAY_KEY_ID else 'MISSING')" 2>/dev/null)

case "$KEY_PREFIX" in
    rzp_live)
        ok "RAZORPAY_KEY_ID is LIVE mode (rzp_live_...)"
        ;;
    rzp_test)
        fail "RAZORPAY_KEY_ID is still TEST mode (rzp_test_...) — update /opt/clinomic-b12-platform/.env and restart backend"
        ;;
    MISSING)
        fail "RAZORPAY_KEY_ID is empty in environment"
        ;;
    *)
        warn "RAZORPAY_KEY_ID has unexpected prefix: $KEY_PREFIX"
        ;;
esac

# ── 3. Verify key secret is present ────────────────────────────────────────
SECRET_LEN=$(docker exec "$BACKEND_CTR" python -c \
    "from django.conf import settings; print(len(settings.RAZORPAY_KEY_SECRET))" 2>/dev/null)

if [ -z "$SECRET_LEN" ] || [ "$SECRET_LEN" = "0" ]; then
    fail "RAZORPAY_KEY_SECRET is empty"
elif [ "$SECRET_LEN" -lt 20 ]; then
    warn "RAZORPAY_KEY_SECRET is suspiciously short ($SECRET_LEN chars)"
else
    ok "RAZORPAY_KEY_SECRET is set ($SECRET_LEN chars)"
fi

# ── 4. Verify webhook secret is present ────────────────────────────────────
WH_SECRET_LEN=$(docker exec "$BACKEND_CTR" python -c \
    "from django.conf import settings; print(len(settings.RAZORPAY_WEBHOOK_SECRET))" 2>/dev/null)

if [ -z "$WH_SECRET_LEN" ] || [ "$WH_SECRET_LEN" = "0" ]; then
    fail "RAZORPAY_WEBHOOK_SECRET is empty"
elif [ "$WH_SECRET_LEN" -lt 16 ]; then
    warn "RAZORPAY_WEBHOOK_SECRET is suspiciously short ($WH_SECRET_LEN chars)"
else
    ok "RAZORPAY_WEBHOOK_SECRET is set ($WH_SECRET_LEN chars)"
fi

# ── 5. Verify migrations 0006 + 0007 are applied ───────────────────────────
MIGRATIONS=$(docker exec "$BACKEND_CTR" python manage.py showmigrations billing 2>/dev/null | grep -E "0006|0007")

if echo "$MIGRATIONS" | grep -q "\[X\] 0006"; then
    ok "Migration 0006 (live pricing) applied"
else
    fail "Migration 0006 NOT applied — run: docker exec $BACKEND_CTR python manage.py migrate billing"
fi

if echo "$MIGRATIONS" | grep -q "\[X\] 0007"; then
    ok "Migration 0007 (live plan IDs) applied"
else
    fail "Migration 0007 NOT applied — run: docker exec $BACKEND_CTR python manage.py migrate billing"
fi

# ── 6. Verify SubscriptionPlan rows in DB ──────────────────────────────────
PLAN_DUMP=$(docker exec "$BACKEND_CTR" python manage.py shell -c "
from apps.billing.models import SubscriptionPlan
for p in SubscriptionPlan.objects.all().order_by('price_monthly'):
    print(f'{p.name}|{p.price_monthly}|{p.monthly_limit}|{p.razorpay_plan_id}')
" 2>/dev/null)

EXPECTED_PLANS=("starter" "growth" "chain" "enterprise")
EXPECTED_PRICES=("7999.00" "17999.00" "27999.00" "0.00")
EXPECTED_LIMITS=("200" "500" "1000" "-1")
EXPECTED_IDS=("plan_ScwbbW9OPk67yP" "plan_ScwcPiAzVQgIzF" "plan_Scwcnke31aFCTm" "")

for i in "${!EXPECTED_PLANS[@]}"; do
    name="${EXPECTED_PLANS[$i]}"
    expected_price="${EXPECTED_PRICES[$i]}"
    expected_limit="${EXPECTED_LIMITS[$i]}"
    expected_id="${EXPECTED_IDS[$i]}"

    row=$(echo "$PLAN_DUMP" | grep "^${name}|" || true)
    if [ -z "$row" ]; then
        fail "Plan '$name' missing from DB"
        continue
    fi

    actual_price=$(echo "$row" | cut -d'|' -f2)
    actual_limit=$(echo "$row" | cut -d'|' -f3)
    actual_id=$(echo "$row" | cut -d'|' -f4)

    if [ "$actual_price" = "$expected_price" ]; then
        ok "Plan '$name' price = ₹$actual_price"
    else
        fail "Plan '$name' price = ₹$actual_price (expected ₹$expected_price)"
    fi

    if [ "$actual_limit" = "$expected_limit" ]; then
        ok "Plan '$name' monthly_limit = $actual_limit"
    else
        fail "Plan '$name' monthly_limit = $actual_limit (expected $expected_limit)"
    fi

    if [ "$name" = "enterprise" ]; then
        if [ -z "$actual_id" ]; then
            ok "Plan '$name' has no razorpay_plan_id (expected — custom pricing)"
        else
            warn "Plan '$name' has razorpay_plan_id=$actual_id (expected empty)"
        fi
    else
        if [ "$actual_id" = "$expected_id" ]; then
            ok "Plan '$name' razorpay_plan_id = $actual_id"
        else
            fail "Plan '$name' razorpay_plan_id = '$actual_id' (expected '$expected_id')"
        fi
    fi
done

# ── 7. Verify "professional" plan no longer exists ─────────────────────────
if echo "$PLAN_DUMP" | grep -q "^professional|"; then
    fail "Old 'professional' plan still in DB — migration 0006 did not run cleanly"
else
    ok "Old 'professional' plan removed (renamed to 'growth')"
fi

# ── 8. Verify webhook endpoint is reachable ────────────────────────────────
WEBHOOK_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    https://clinomiclabs.com/api/billing/webhook/razorpay \
    -H "Content-Type: application/json" \
    -d '{"event":"test"}' 2>/dev/null)

case "$WEBHOOK_HTTP" in
    400|401)
        ok "Webhook endpoint reachable (returns $WEBHOOK_HTTP — invalid sig as expected)"
        ;;
    503)
        fail "Webhook endpoint returns 503 — RAZORPAY_WEBHOOK_SECRET likely missing"
        ;;
    404)
        fail "Webhook endpoint returns 404 — URL routing broken"
        ;;
    000)
        fail "Webhook endpoint unreachable (TLS or DNS issue)"
        ;;
    *)
        warn "Webhook endpoint returned unexpected status: $WEBHOOK_HTTP"
        ;;
esac

# ── 9. Verify health endpoint ──────────────────────────────────────────────
HEALTH_HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
    https://clinomiclabs.com/api/health/ready 2>/dev/null)

if [ "$HEALTH_HTTP" = "200" ]; then
    ok "Backend /api/health/ready returns 200"
else
    fail "Backend /api/health/ready returns $HEALTH_HTTP"
fi

# ── 10. Check Razorpay client can authenticate (live API ping) ─────────────
API_PING=$(docker exec "$BACKEND_CTR" python -c "
import razorpay
from django.conf import settings
try:
    c = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    # Cheap call — list plans (returns even if zero plans)
    c.plan.all({'count': 1})
    print('OK')
except Exception as e:
    print(f'FAIL:{type(e).__name__}:{str(e)[:80]}')
" 2>/dev/null)

if [ "$API_PING" = "OK" ]; then
    ok "Razorpay API authentication successful (live key valid)"
else
    fail "Razorpay API auth failed: $API_PING"
fi

# ── Summary ────────────────────────────────────────────────────────────────
echo
echo "=========================================="
echo "  Summary"
echo "=========================================="
echo -e "  ${GREEN}Pass: $PASS${RESET}   ${RED}Fail: $FAIL${RESET}   ${YELLOW}Warn: $WARN${RESET}"
echo

if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}✅ PAYMENTS ARE LIVE${RESET}"
    echo
    echo "Next steps:"
    echo "  1. Make a small real-card test transaction on the Starter plan"
    echo "  2. Verify subscription appears in Razorpay dashboard"
    echo "  3. Check PaymentEvent table for 'subscription.activated' event"
    exit 0
else
    echo -e "${RED}❌ NOT READY — fix the FAIL items above${RESET}"
    exit 1
fi

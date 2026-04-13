# Razorpay Live Mode — Go-Live Checklist

This document tracks the current Razorpay integration state and the exact
steps remaining to flip from **test mode** to **live mode**.

Last updated: 2026-04-13 after KYC-blocked rollback.

---

## Current state (test mode)

The platform is running on Razorpay **test** API keys. Subscriptions can be
created and tested end-to-end using test cards. No real charges occur.

### Active plan IDs in DB

| Plan | Price (display) | Test plan ID (current) | Live plan ID (when KYC clears) |
|---|---|---|---|
| `starter` | ₹7,999/mo · 200 analyses | `plan_SJY8pfd6y3BUnX` *(test ₹2999)* | `plan_ScwbbW9OPk67yP` |
| `growth` | ₹17,999/mo · 500 analyses | `plan_SJY9erA6p5Mcjs` *(test ₹7999)* | `plan_ScwcPiAzVQgIzF` |
| `chain` | ₹27,999/mo · 1000 analyses | *(none — no test plan)* | `plan_Scwcnke31aFCTm` |
| `enterprise` | Custom pricing | *(none)* | *(none — handled via sales)* |

> **Note:** the DB column `price_monthly` shows the **display price** (₹7999 / ₹17999 / ₹27999),
> but the underlying test plans have the OLD prices (₹2999 / ₹7999) because that's what
> exists in Razorpay test mode. This is fine for QA / development. Customers seeing
> the test checkout will see the test prices, not the display prices.

---

## When KYC clears — the 4-step swap

1. **Get live API credentials from Razorpay dashboard** (Settings → API Keys, Live mode):
   - `RAZORPAY_KEY_ID` — starts with `rzp_live_`
   - `RAZORPAY_KEY_SECRET` — shown only once at generation
   - `RAZORPAY_WEBHOOK_SECRET` — the value you set when creating the live webhook

2. **Update `.env` on production server**:
   ```bash
   ssh -o HostKeyAlgorithms=+ssh-rsa root@66.116.225.67
   nano /opt/clinomic-b12-platform/.env
   # Replace these 3 lines:
   #   RAZORPAY_KEY_ID=rzp_live_xxxxxxxxx
   #   RAZORPAY_KEY_SECRET=<live secret>
   #   RAZORPAY_WEBHOOK_SECRET=<live webhook secret>
   ```

3. **Swap DB plan IDs back to live**:
   ```bash
   docker exec clinomic-b12-platform-backend-1 python manage.py shell -c "
   from apps.billing.models import SubscriptionPlan
   SubscriptionPlan.objects.filter(name='starter').update(razorpay_plan_id='plan_ScwbbW9OPk67yP')
   SubscriptionPlan.objects.filter(name='growth').update(razorpay_plan_id='plan_ScwcPiAzVQgIzF')
   SubscriptionPlan.objects.filter(name='chain').update(razorpay_plan_id='plan_Scwcnke31aFCTm')
   print('Live plan IDs restored.')
   "
   ```

4. **Restart backend and verify**:
   ```bash
   cd /opt/clinomic-b12-platform
   docker-compose -f docker-compose.prod.yml restart backend
   sleep 15
   bash scripts/verify-razorpay-live.sh
   ```

---

## Razorpay dashboard configuration

### Webhook URL — IMPORTANT

The correct webhook URL is:

```
https://clinomiclabs.com/api/billing/webhook/
```

⚠️ **Not** `/api/billing/webhook/razorpay` (this 404s — fixed in commit 30009fc).

Set this in **both** test mode and live mode webhooks (Settings → Webhooks).

### Subscribed events (live mode)

- `subscription.activated`
- `subscription.charged`
- `subscription.cancelled`
- `subscription.completed`
- `subscription.halted`
- `payment.failed`

### KYC checklist (Razorpay activation requirements)

For healthcare/medical SaaS in India, Razorpay typically requires:

- **PAN card** (business or proprietor)
- **Bank account proof** (cancelled cheque or bank statement)
- **GST registration** (if applicable; required above ₹20L turnover)
- **Business proof**: Certificate of Incorporation, Partnership Deed, or Shop & Establishment Act licence
- **Address proof** for the registered business address
- **Director/proprietor identity proof** (Aadhar + PAN)

If you are stuck on activation, check **Account & Settings → Account Activation**
in the dashboard. The page lists exactly which items are pending.

For healthcare specifically, Razorpay may also ask for:
- Medical practice license / clinical establishment registration
- A short business description explaining the SaaS model (helps reviewers
  understand you're not a pharmacy or telemedicine provider)

If activation is taking more than 3 business days, raise a ticket via the
dashboard help icon — quote your merchant ID.

---

## Existing test subscriptions (do not delete)

These are real records in the production DB created during test-mode QA:

| Org | Plan | Status | razorpay_sub_id |
|---|---|---|---|
| Satani Research Centre | starter | active | sub_SR5itFVnt7AA71 |
| PulsePath Laboratory | starter | expired | (none) |
| Sparsh Pathology | starter | expired | (none) |
| Clinomic Platform | enterprise | expired | sub_ScwnPhtHcHXBKZ |

When live mode launches, these test subscriptions will continue to reference
test plan IDs which still exist on Razorpay's side. They won't be billed
in live mode. New signups after the swap will use live plans.

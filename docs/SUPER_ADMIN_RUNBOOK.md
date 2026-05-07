# SUPER_ADMIN Runbook — Clinomic B12 SaaS

The platform owner's reference. You hold both `role=SUPER_ADMIN` and `is_superuser=True` — most permission classes accept either, you have both.

The codebase has exactly one SUPER_ADMIN role and (at the time of writing) one human account holding it. Everything in this file is scoped to *your* operational concerns, not to LAB or DOCTOR users.

---

## 1. Capabilities

### Platform-only endpoints (`/api/v1/platform/...`)

Gated by `IsPlatformSuperAdmin`. No other role can reach these.

| Verb + path | Effect |
|---|---|
| `GET    /platform/stats/` | Cross-org KPIs (orgs, users, screenings, MRR) |
| `GET    /platform/orgs/` | List every tenant on the SaaS |
| `POST   /platform/orgs/create/` | Provision new tenant (schema + owner user + sub) |
| `GET    /platform/orgs/<schema>/` | Full state for one org |
| `PATCH  /platform/orgs/<schema>/` | Suspend / reactivate (revokes all org tokens on suspend) |
| `DELETE /platform/orgs/<schema>/` | Hard-delete: drops the schema, all users, all data |
| `POST   /platform/orgs/<schema>/plan/` | Override plan without Razorpay |
| `GET    /platform/orgs/<schema>/usage/` | Any org's usage history |
| `GET    /platform/orgs/<schema>/users/` | Any org's user list |
| `POST   /platform/orgs/<schema>/users/` | Create a user inside any org |
| `POST   /platform/orgs/<schema>/resend-credentials/` | Resend creds email |

Source: [apps/core/platform_views.py](../backend_v3/apps/core/platform_views.py).

### Cross-tenant analytics

`required_roles = [Role.SUPER_ADMIN]`:
- Population cohorts (cross-org B12 risk distributions)
- Population trends (longitudinal)
- Lab comparison rankings
- Cross-org doctor stats

Source: [apps/analytics/views.py](../backend_v3/apps/analytics/views.py).

### Inherited LAB powers

You match `required_roles=[any]` because `is_superuser=True`. Anything a LAB admin can do — billing, plan upgrades, API keys, webhooks, user CRUD, lab/doctor records, screening reviews, FHIR — is also yours.

### Special bypasses

1. **MFA endpoint bypass** — [permissions.py:178](../backend_v3/apps/core/permissions.py#L178). `IsMFAVerified` exempts SUPER_ADMIN. You still complete MFA at *login*, but per-endpoint MFA gating is skipped.
2. **HasRole bypass** — [permissions.py:71](../backend_v3/apps/core/permissions.py#L71). `is_superuser=True` short-circuits any role check.
3. **Tenant scope bypass** — `JWTTenantMiddleware` accepts an `X-Org-Id` header from you, switching the request schema.
4. **MFA management on others** — disable / regenerate / force-reset MFA on any user.

### What you CANNOT do

- **Impersonate another user's JWT.** You operate from your own token.
- **Decrypt PHI without the master key.** Patient name/age/sex are Fernet-encrypted at rest; no role bypass.
- **Bypass webhook signature verification** — `AllowAny` endpoint, signature is canonical.

---

## 2. Day-to-day platform ops

### Create a new tenant
```bash
curl -X POST https://clinomiclabs.com/api/v1/platform/orgs/create/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Acme Lab","schema_name":"acme","plan":"pilot","owner":{"username":"acme_admin","email":"admin@acmelab.com"}}'
```
The response includes a one-time generated password emailed to the owner.

### Suspend an org (dispute, non-payment, etc.)
```bash
curl -X PATCH https://clinomiclabs.com/api/v1/platform/orgs/<schema>/ \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"action":"suspend"}'
```
**All users in that org lose their sessions immediately** (refresh tokens revoked + min-iat bumped). They get logged out next request.

### Reactivate
Same endpoint, `{"action":"reactivate"}`.

### Hard-delete an org
**Irreversible.** Drops the entire tenant Postgres schema:
```bash
curl -X DELETE https://clinomiclabs.com/api/v1/platform/orgs/<schema>/ \
  -H "Authorization: Bearer $TOKEN"
```
Take a backup first if there's any chance you'll need the data — `pg_dump` on the tenant schema before calling this.

### Override a plan (skip Razorpay)
For comping a customer or fixing a stuck billing state:
```bash
curl -X POST https://clinomiclabs.com/api/v1/platform/orgs/<schema>/plan/ \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"plan":"professional"}'
```

### Reset a stuck user's MFA
SSH into prod, then:
```bash
docker exec -it clinomic-b12-platform-backend-1 python manage.py shell
```
```python
from apps.core.models import User, MFASettings
u = User.objects.get(username='stuck_user')
u.mfa_settings.delete()  # forces fresh setup at next login
```
Or use the bulk-fix script in `feedback_mfa_email_only.md` memory for multiple users.

---

## 3. Recovery flows

### You forgot your password / lost MFA
SSH into prod:
```bash
ssh -o HostKeyAlgorithms=+ssh-rsa root@66.116.225.67
docker exec -it clinomic-b12-platform-backend-1 \
  python manage.py reset_superadmin
```
That deactivates **all** current SUPER_ADMINs and creates a fresh one with secure defaults (prints the new credentials once). Source: [reset_superadmin.py](../backend_v3/apps/core/management/commands/reset_superadmin.py).

### You lost SSH access
You're in trouble. Mitigations to put in place *before* this happens:
- Keep the SSH private key in a password manager (1Password, Bitwarden) on a device that isn't the one you SSH from.
- Keep a second SSH key authorized on `root@66.116.225.67` from a backup laptop.
- Save the BigRock VPS console login — you can reach a serial console without SSH.

### You lost the master encryption key
PHI is unrecoverable. The key lives in `/opt/clinomic-b12-platform/.env` as `MASTER_ENCRYPTION_KEY`. Backup that file *off-server* (encrypted) — see [BACKUP_SETUP.md](BACKUP_SETUP.md).

### Your JWT was compromised
Revoke all your tokens via shell:
```bash
docker exec -it clinomic-b12-platform-backend-1 python manage.py shell
```
```python
from apps.core.models import User
from apps.core.authentication import revoke_all_user_tokens
revoke_all_user_tokens(User.objects.get(username='<your-username>'))
```
Then change your password and re-enable MFA. The revoke_all_user_tokens call kills both access and refresh tokens immediately (see [authentication.py:48](../backend_v3/apps/core/authentication.py#L48)).

---

## 4. Risks specific to solo SUPER_ADMIN

| Risk | Mitigation |
|---|---|
| Account compromise → full platform breach | Strong unique password + MFA + don't share the email |
| Lost access → no second admin to recover | `reset_superadmin` via SSH is the lever. Keep SSH access redundant. |
| MFA endpoint bypass means stolen JWT is fully powered | Short access-token lifetime (15min) + refresh-token revocation reduce blast radius |
| No "SUPER_ADMIN action log" beyond standard logs | Grep `structlog` output for `user=<your-username>` (`grafana → loki`) |
| You demote yourself by accident | Token revocation will lock you out. Recover via `reset_superadmin`. |

---

## 5. Audit / observability

Every platform endpoint emits a `structlog` line on success and warning on suspicious paths:
- `platform.org_status_changed` — suspend/reactivate
- `platform.org_deleted` — hard-delete
- `billing.payment_verified` / `billing.payment_verify_org_mismatch` — payment ops
- `billing.webhook_*` — Razorpay webhook activity

Logs are aggregated to Grafana Loki at `https://clinomiclabs.com/grafana/`. To find your activity:
```
{user="<your-username>"} | json
```

The `audit` app (`apps.core.audit`) records signed PHI access events separately — see [DATA_MINIMISATION_AUDIT.md](DATA_MINIMISATION_AUDIT.md).

---

## 6. Token revocation behavior (post-Apr 2026)

Any of these admin-driven actions now invalidates the target user's outstanding access **and** refresh tokens immediately:

- `PATCH /admin/users/<id>` with role / is_active / password change
- `DELETE /admin/users/<id>` (soft + hard)
- `PATCH /platform/orgs/<schema>/` action=suspend
- `DELETE /platform/orgs/<schema>/`
- `POST /mfa/verify-setup` (mints fresh MFA-verified tokens for the actor)

Revocation works via:
1. `RefreshToken.is_revoked = True` — kills long-term sessions
2. Per-user `jwt_min_iat:<user_id>` Redis key — kills outstanding access tokens

Source: [authentication.py:revoke_all_user_tokens](../backend_v3/apps/core/authentication.py).

If revocation must NOT fire (e.g. self-edits where you keep your session), the helper is at the call-site and can be conditionally bypassed.

---

## 7. Quick links

- General prod runbook: [RUNBOOK.md](RUNBOOK.md)
- Backup procedures: [BACKUP_SETUP.md](BACKUP_SETUP.md)
- Restore drill: [RESTORE_TEST.md](RESTORE_TEST.md)
- Razorpay go-live: [GO_LIVE_RAZORPAY.md](GO_LIVE_RAZORPAY.md)
- Incident response: [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)
- Least-privilege model: [LEAST_PRIVILEGE.md](LEAST_PRIVILEGE.md)

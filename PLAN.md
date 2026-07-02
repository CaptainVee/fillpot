# FillPot — Implementation Blueprint

## Context

FillPot is a Django 5.2 group contribution platform that replaces the Nigerian WhatsApp-bank-transfer-screenshot workflow. Organisers create pots, contributors each receive a dedicated Nomba virtual account (NUBAN), and every inbound bank transfer is automatically reconciled to the right person via Nomba's webhook. The project is built for a Nomba hackathon, targeting the "Virtual Accounts as Infrastructure" track.

**Confirmed decisions:**
- SQLite locally, Postgres in production (via `DATABASE_URL`)
- Email + password auth; single `User` model — roles are contextual, not model-level
- Celery + Redis from day one
- Django templates + HTMX (SSE for live feed)
- Brevo SMTP for email
- Hosting TBD (Railway/EC2/Linode — design for portability)

---

## Project Structure

```
fillpot/                              ← repo root
├── requirements/
│   ├── base.txt                      ← Django, psycopg2-binary, dj-database-url, redis,
│   │                                    celery[redis], django-celery-beat, python-dotenv,
│   │                                    requests, structlog
│   ├── local.txt                     ← base + django-debug-toolbar
│   └── production.txt                ← base + uvicorn[standard], whitenoise
├── .env.example
├── Procfile                          ← web: uvicorn, worker: celery, beat: celery beat
│
├── fillpot/                          ← project package
│   ├── celery.py                     ← Celery app + beat_schedule
│   ├── asgi.py                       ← unchanged; Django 5.2 handles async views natively
│   ├── urls.py
│   └── settings/
│       ├── base.py                   ← AUTH_USER_MODEL, CELERY_*, INSTALLED_APPS, REDIS_URL
│       ├── local.py                  ← DEBUG=True, SQLite
│       └── production.py             ← dj-database-url, WhiteNoise, HTTPS headers
│
├── accounts/                         ← User model (email auth) + auth views
├── pots/                             ← Pot, Withdrawal models; organiser + public views; SSE
├── contributions/                    ← Contributor, Contribution, Pledge models + join flow
│   └── reconciliation.py             ← pure state machine, no ORM imports at module level
├── payments/                         ← NombaClient, Payment model, webhook endpoint
│   ├── client.py
│   ├── exceptions.py
│   └── views.py                      ← @csrf_exempt webhook
├── notifications/                    ← Celery email tasks only; receives primitive args
│
├── templates/
│   ├── base.html                     ← Tailwind CDN, HTMX CDN + SSE extension
│   ├── accounts/
│   ├── pots/
│   │   ├── public_pot.html           ← SSE live feed + progress bar
│   │   └── organiser_detail.html
│   └── contributions/
│       ├── join.html
│       └── account_displayed.html    ← shows NUBAN after form submit
└── static/
```

---

## Data Models

### accounts — User (Custom User)
`AbstractBaseUser + PermissionsMixin`. `USERNAME_FIELD = 'email'`. `AUTH_USER_MODEL = 'accounts.User'`.

**Roles are contextual, not model-level.** A `User` becomes an organiser by creating a pot; a contributor by joining one. No separate profile models.

| Field | Type |
|---|---|
| id | UUIDField(primary_key=True) |
| email | EmailField(unique=True) |
| full_name | CharField(120) |
| is_active / is_staff | BooleanField |
| date_joined | DateTimeField(auto_now_add) |

---

### pots — Pot

| Field | Notes |
|---|---|
| id | UUID PK |
| organiser | FK → settings.AUTH_USER_MODEL (PROTECT) |
| slug | SlugField(unique, 20) — `slugify(name)[:12] + '-' + uuid4().hex[:6]` |
| name, description, occasion_type | display |
| pot_type | choices: CONTRIBUTION / PLEDGE |
| target_amount | DecimalField, nullable |
| deadline | DateTimeField, nullable |
| status | choices: ACTIVE / CLOSED / CANCELLED; indexed |
| total_collected | DecimalField(default=0) — denormalized, updated with `F()` |
| contributor_count | PositiveIntegerField(default=0) — denormalized, updated with `F()` |

Index: `(organiser, status)` for dashboard; `status` for expiry job.

---

### pots — Withdrawal

| Field | Notes |
|---|---|
| id | UUID PK |
| pot | OneToOneField(Pot) — DB-level one-withdrawal-per-pot guard |
| bank_code, account_number, account_name | recipient details |
| amount_naira | snapshot of total_collected at withdrawal time |
| nomba_tx_ref | CharField(unique) — idempotency key sent to Nomba |
| status | PENDING / SUCCESS / FAILED |
| failure_reason | TextField(blank) |

---

### contributions — Contributor

| Field | Notes |
|---|---|
| id | UUID PK |
| pot | FK → Pot |
| user | FK → settings.AUTH_USER_MODEL, null=True, on_delete=SET_NULL — null for guests |
| full_name, email | always stored for display and receipts, even for registered users |
| is_anonymous | hides name on public feed |
| wants_group_notifications | opt-in to every payment alert |
| virtual_account_id | CharField(unique) — **hot webhook lookup path**; indexed |
| virtual_account_number | NUBAN shown to contributor |
| virtual_account_bank_name | display |

Constraint: `unique_together = [('pot', 'email')]` — same email on same pot reuses existing NUBAN.

**Guest claim:** On user registration, run `Contributor.objects.filter(email=user.email, user=None).update(user=user)` to retroactively link all prior guest contributions to the new account.

---

### contributions — Contribution (Contribution Pot aggregate)

| Field | Notes |
|---|---|
| contributor | OneToOneField → Contributor |
| intended_amount | declared at sign-up |
| total_paid | DecimalField(default=0) — updated with `F()` on each webhook |
| status | PENDING → CONFIRMED / PARTIAL / OVERPAID |
| confirmed_at | DateTimeField(null) |

---

### contributions — Pledge (Pledge Pot aggregate)

| Field | Notes |
|---|---|
| contributor | OneToOneField → Contributor |
| pledged_amount | total commitment |
| total_paid | running sum, `F()` incremented |
| is_complete | True when total_paid ≥ pledged_amount |
| last_payment_at | drives 7-day reminder job |

Index: `(is_complete, last_payment_at)` for reminder job.

---

### payments — Payment (raw ledger, one row per webhook event)

| Field | Notes |
|---|---|
| nomba_request_id | CharField(unique) — **primary idempotency key** |
| contributor | FK → Contributor |
| amount_naira / amount_kobo | both stored; kobo is canonical |
| event_type | `"virtual_account.funded"` etc. |
| merchant_tx_ref | CharField(unique) — for `/transactions` reconciliation |
| sender_name, sender_account | from webhook data |
| raw_payload | JSONField — enables reprocessing |
| processed_at | DateTimeField(auto_now_add) |

---

## NombaClient Design (`payments/client.py`)

**Token lifecycle:** Redis key `fillpot:nomba:access_token`, TTL 3300s (55 min). On cache miss, acquire Redis lock `fillpot:nomba:token:lock` (SET NX EX 10) to prevent stampede, call `/auth/token/issue`, store result. All workers share one cached token.

**Amount helpers:**
- `to_kobo(Decimal) → int` — always use before any outbound API call
- `from_kobo(int) → Decimal` — always use on inbound webhook amounts

**`_request(method, path, **kwargs)`:** Gets token, sets `Authorization: Bearer` + `accountId` headers, 10s timeout. On 401: evict cache, retry once. On 5xx: raise `NombaAPIError`. Logs every call with `structlog` tagging `merchantTxRef`.

**Public methods:**
- `create_virtual_account(customer_name, email, customer_ref)` — `customer_ref = str(contributor.id)`
- `lookup_bank_account(bank_code, account_number)` — returns `accountName` for organiser confirmation
- `transfer(amount_naira, bank_code, account_number, account_name, narration, merchant_tx_ref)` — caller must pre-generate and persist `merchant_tx_ref` before calling
- `get_transactions(date_from, date_to, status='success')` — for nightly reconciliation task
- `expire_virtual_account(virtual_account_id)` — stub-safe if endpoint unavailable in sandbox

---

## Webhook Flow (`payments/views.py`)

`@csrf_exempt POST /api/v1/webhooks/nomba/`

1. **Capture `request.body`** before any parsing.
2. **HMAC verify:** `hmac.new(SECRET.encode(), body, sha256).hexdigest()` vs `nomba-signature` header using `hmac.compare_digest()`. Return 401 on mismatch.
3. **Parse JSON.** Return 400 on malformed.
4. **Idempotency:** `Payment.objects.filter(nomba_request_id=event['requestId']).exists()` → return 200 if found. **Also catch `IntegrityError` on insert** (safe under concurrent Postgres workers).
5. **Route event type.** Only process `virtual_account.funded` here; handle `transfer.success/failed` to update Withdrawal.status.
6. **Contributor lookup** by `virtual_account_id`. `DoesNotExist` → log + return 200.
7. **Pot status check.** If `CLOSED/CANCELLED` → return 200.
8. **`transaction.atomic()`:**
   - `Payment.objects.create(...)` — catch `IntegrityError` → return 200
   - `reconciliation.process(contributor, amount_naira)` → returns `ReconciliationResult`
   - If `result.is_first_payment`: `Pot.objects.filter(pk=pot.pk).update(contributor_count=F('contributor_count') + 1)`
   - Always: `Pot.objects.filter(pk=pot.pk).update(total_collected=F('total_collected') + amount_naira)`
9. **`transaction.on_commit()`** (fires only after DB commit):
   - `redis.publish(f'fillpot:pot:{pot.id}:feed', json_payload)` — drives SSE
   - Queue Celery email tasks: receipt, organiser notification, group notifications (if opted in), overpayment alert (if overpaid)
10. Return 200.

### Reconciliation state machine (`contributions/reconciliation.py`)

Pure function, no HTTP/ORM side effects at module level — unit-testable without DB.

**Contribution Pot:**
- `new_total == intended` → CONFIRMED; set `confirmed_at`
- `new_total < intended` → PARTIAL
- `new_total > intended` → OVERPAID
- `is_first_payment = (new_total == amount_naira)` — i.e. total was zero before

**Pledge Pot:**
- Accumulate `total_paid`; if `total_paid >= pledged_amount` → `is_complete=True`
- Always update `last_payment_at`
- `is_first_payment` same logic

---

## SSE Live Feed

```
Webhook → reconciliation (DB) → redis.publish (on_commit)
                                        ↓
Browser ← StreamingHttpResponse ← async Django view ← redis async subscribe
```

**Async view** (`pots/views.py`):
- `async def pot_feed(request, slug)` returns `StreamingHttpResponse`
- One-time ORM lookup: `await sync_to_async(Pot.objects.get)(slug=slug)`
- `redis.asyncio.Redis` subscriber on channel `fillpot:pot:{pot_id}:feed`
- Loop: `await asyncio.wait_for(pubsub.get_message(...), timeout=25.0)` → yield SSE message; on timeout yield `: keepalive\n\n`
- Break on `await request.is_disconnected()`
- Headers: `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`

**HTMX integration:** `hx-ext="sse"`, `sse-connect="/p/{slug}/feed/"`. SSE payload is JSON; a small `<script>` block on the page handles rendering the feed entry and updating the progress bar. Avoids server-side template rendering per event.

**Production server:** Must be `uvicorn fillpot.asgi:application`. Sync Gunicorn workers cannot hold long-lived SSE connections.

---

## Feature Phases

| # | Phase | Deliverable | Depends on |
|---|---|---|---|
| 1 | **Foundation** | Settings split, custom `User` model (email auth, contextual roles), requirements files, Celery init | — (must be first; custom user can't be added after first migration) |
| 2 | **Pot CRUD** | User signup/login (with guest-claim on register), create pot, slug generation, dashboard list | Phase 1 |
| 3 | **Contributor flow (no payments)** | Public pot page, join form, Contributor / Contribution / Pledge models | Phase 2 |
| 4 | **Nomba virtual accounts** | NombaClient, `create_virtual_account` on join, NUBAN shown to contributor | Phase 3 + ngrok configured |
| 5 | **Webhook + reconciliation** | Payment model, webhook endpoint, HMAC, idempotency, state machine, unit tests | Phase 4 |
| 6 | **SSE live feed** | Redis publish in webhook, async streaming view, HTMX SSE, progress bar | Phase 5 + Redis running |
| 7 | **Email notifications** | Brevo SMTP config, all Celery email tasks and templates | Phase 5 |
| 8 | **Organiser dashboard + withdrawal** | Contributor history, overpayment flags, withdrawal form + lookup + transfer | Phase 5 |
| 9 | **Background jobs** | `expire_due_pots` (hourly), `send_pledge_reminders` (daily 9am WAT), `reconcile_with_nomba` (nightly 2am) | Phases 5, 7 |
| 10 | **Deployment prep** | `production.py` hardening, WhiteNoise, `/health/` endpoint, `.env.example`, Procfile | All phases |

---

## Risks and Tradeoffs

**1. Concurrent webhook race condition (SQLite masks this)**
SQLite serialises writes; Postgres does not. Two simultaneous webhook deliveries for the same `requestId` can both pass a `filter().exists()` check before either commits. Fix: rely solely on the `unique=True` constraint + catch `IntegrityError` on insert. Use `F()` expressions for all counter increments from day one.

**2. Virtual account creation blocks the request**
Calling Nomba's API synchronously in the join view means contributors wait. Mitigation: 5s timeout + clean retry page on `NombaAPIError`. Async creation via Celery is more resilient but doubles join flow complexity — not worth it for the hackathon.

**3. SSE + async Django + production worker**
Any sync Gunicorn worker exhausts under SSE load. Commit to `uvicorn` from Phase 1. Any ORM call inside the async SSE generator must be wrapped in `sync_to_async()`.

**4. Nomba webhook delivery to localhost**
Nomba can't reach `localhost:8000`. Use ngrok from Phase 4. Also write `manage.py fire_test_webhook --amount 5000 --virtual-account-id <id>` that signs a fake payload and POSTs locally — removes ngrok dependency for unit testing.

**5. `CELERY_TASK_ALWAYS_EAGER` breaks `on_commit()` pattern**
`ALWAYS_EAGER=True` executes tasks before the DB transaction commits, breaking the `on_commit()` pattern. Keep `ALWAYS_EAGER=False` locally and run a real Redis + Celery worker. A `docker-compose.yml` with `redis` and `celery-worker` services makes this one command.

**6. Denormalized counter drift**
`total_collected` and `contributor_count` can drift on bugs. The nightly reconciliation task should also recompute `SUM(Payment.amount_naira)` per pot and compare to `Pot.total_collected`, self-healing on drift. `contributor_count` increments only when `is_first_payment=True` — test this explicitly.

---

## Critical Files (order matters)

1. `fillpot/settings/base.py` — `AUTH_USER_MODEL = 'accounts.User'`, `INSTALLED_APPS`, `REDIS_URL`, `CELERY_*`; correct before first `migrate`
2. `accounts/models.py` — custom `User` model (`AbstractBaseUser`, email as username); referenced by all FK targets
3. `payments/client.py` — NombaClient; all integration phases depend on this
4. `contributions/reconciliation.py` — pure state machine; most business-critical logic
5. `payments/views.py` — webhook endpoint; ties together HMAC, idempotency, reconciliation, SSE, Celery

---

## Verification Checklist

- [ ] `manage.py fire_test_webhook --amount 25000` → Payment row created, Contribution status = CONFIRMED
- [ ] Underpayment: fire 10,000 against intended 25,000 → PARTIAL; fire 15,000 → CONFIRMED
- [ ] Overpayment: fire 30,000 against intended 25,000 → OVERPAID
- [ ] Two browser tabs open on public pot page; fire test webhook; both update without refresh
- [ ] Contribution receipt arrives in inbox within 30s of webhook
- [ ] Withdrawal form resolves account name via Nomba lookup; transfer fires; Withdrawal.status updates on `transfer.success`
- [ ] `Pot.deadline = now() - 1min`; run `expire_due_pots` manually; pot closes, closure email sent
- [ ] `/health/` returns 200; `DEBUG=False` with `ALLOWED_HOSTS` set; `collectstatic` succeeds

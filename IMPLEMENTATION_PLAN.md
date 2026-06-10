# FraudDetect — Second Expansion Implementation Plan

This plan covers the 7 **new** systems requested on top of the already-shipped
9-feature expansion (tags, global search, notifications + SSE real-time, bulk
admin transactions, transaction detail drawer, audit-log service, admin users
page, live dashboard). It is split into three phases so each can be built,
verified, and reviewed independently.

**Stack (unchanged):** FastAPI + MongoDB Atlas + React/Vite.
**Decisions for this expansion:** keep MongoDB (no Postgres migration); email via
a pluggable SMTP service with a dev/console fallback; phased delivery.

---

## Phase map

| Phase | Systems | Spec features |
|-------|---------|----------------|
| **1 — Account & control core** | User balance, credit-limit management, user blocking, transaction blocking rules, fraud auto-blocking, expanded security audit logging, admin user-management controls | 1, 2, 3, 4, 5, 8, 9 |
| **2 — Identity & verification** | Email verification (OTP), login 2FA, login history / device / IP tracking | 6, 7 |
| **3 — Experience & docs** | Modern dashboard redesign, dark/light mode, balance & credit-utilization widgets, notification polish; full deliverables docs (architecture, schema, API reference, security review) | 16 + deliverables |

Features 10–15 (transaction detail, live dashboard, real-time fraud alerts,
search, tags, bulk creation) already exist from the first expansion and are only
extended where the new systems touch them.

---

## Architecture (after expansion)

```
                         ┌────────────────────────────────────────────┐
   React SPA  ──REST──►  │  FastAPI                                    │
      ▲                  │   routes/  auth, transactions, search,      │
      │                  │           admin, admin_tx, account,         │
      │                  │           blocking, rules, fraud_config,    │
      │                  │           notifications, verification       │
      │   SSE  ◄─────────│   services/ events(EventBroker), notifs,    │
      │  /api/stream     │            audit, search, account,          │
      │                  │            rules_engine, fraud_config, email │
      │                  └───────┬───────────────────────┬─────────────┘
      │                          │                       │
      │                   MongoDB Atlas            SMTP (pluggable;
      │            users, transactions,             dev = console)
      │            detection_results, notifications,
      │            audit_logs, transaction_rules,
      │            fraud_config, fraud_events,
      │            account_events, user_status_events,
      │            email_verifications, login_attempts
      └────────── EventBroker fans fraud alerts + data-change events
                  to the affected user and all admins
```

Fraud Engine = Isolation Forest (CSV path) + rule-based scorer (manual path),
now wrapped by a **rules engine** (pre-processing block rules) and a **fraud
auto-block** stage (post-scoring threshold action).

---

## Phase 1 — data model (MongoDB, additive & backward-compatible)

### `users` — new fields (all default sensibly when absent)
```
status: "active" | "suspended" | "blocked" | "under_review"   (default "active")
account: {
  credit_limit:    float   # credit ceiling (default 5000)
  current_balance: float   # credit used / amount owed (default 0)
  total_spending:  float   # lifetime approved spend
  total_deposits:  float   # lifetime payments / admin-added funds
  total_transactions: int
  is_frozen:       bool    # blocks new spends
  credit_suspended: bool   # credit line temporarily suspended (limit treated as 0)
  currency:        "USD"
  updated_at:      datetime
}
block: {                   # present only while blocked / historically last block
  reason_code, reason, notes, blocked_by, blocked_by_email, blocked_at,
  unblocked_by, unblocked_at, unblock_notes
}
email_verified: bool       # seeded true for existing users; used in Phase 2
force_2fa: bool            # Phase 2
```
`available_credit` is **derived**: `credit_limit - current_balance` (0 when
`credit_suspended`). Existing users without `account` are treated as a default
account on read and lazily initialised on first write.

### New collections
- **`transaction_rules`** — `{ name, rule_type(merchant|category|amount_range|country|card_type|user), config{...}, action(block|flag), enabled, trigger_count, created_by, created_at, updated_at }`
- **`fraud_config`** — single settings doc `{ auto_block_threshold(0-100), auto_flag_threshold, flag_account_on_block(bool), notify_admins(bool), updated_by, updated_at }`
- **`fraud_events`** — `{ transaction_id, user_id, fraud_score, severity, threshold, action(blocked|flagged), reason, created_at }`
- **`account_events`** — user-visible financial history `{ user_id, type(add_funds|remove_funds|set_balance|credit_limit_change|freeze|unfreeze|reset|spend|auto_block), amount?, before, after, actor_id, actor_email, note, created_at }` (doubles as credit-limit history)
- **`user_status_events`** — block/unblock/status history `{ user_id, action, reason_code, reason, notes, actor_id, actor_email, created_at }`

### Indexes (added idempotently in `init_db`)
`users.status`; `transaction_rules.(enabled, rule_type)`; `fraud_events.(user_id, created_at)`, `fraud_events.created_at`; `account_events.(user_id, created_at)`; `user_status_events.(user_id, created_at)`. Audit-log indexes already exist.

---

## Phase 1 — endpoints

**Account / balance (user + admin)**
```
GET   /api/account/me                         user's own balance summary
GET   /api/account/me/history                 own balance + credit-limit history
GET   /api/admin/users/{id}/account           full account + history (admin)
POST  /api/admin/users/{id}/account/add-funds       {amount, note}
POST  /api/admin/users/{id}/account/remove-funds    {amount, note}
PATCH /api/admin/users/{id}/account/balance         {balance, note}  set exact
PATCH /api/admin/users/{id}/account/credit-limit    {credit_limit | delta, note}
POST  /api/admin/users/{id}/account/credit-suspend  toggle credit suspension
POST  /api/admin/users/{id}/account/freeze          freeze / unfreeze balance
POST  /api/admin/users/{id}/account/reset           reset balance to 0
```

**User blocking / status (admin)**
```
POST  /api/admin/users/{id}/block        {reason_code, reason?, notes?}
POST  /api/admin/users/{id}/unblock      {notes?}
PATCH /api/admin/users/{id}/status       {status, notes?}  (suspend/under_review/active)
GET   /api/admin/users/{id}/status-history
```

**Transaction rules (admin)**
```
GET    /api/admin/transaction-rules
POST   /api/admin/transaction-rules
PATCH  /api/admin/transaction-rules/{id}
POST   /api/admin/transaction-rules/{id}/toggle
DELETE /api/admin/transaction-rules/{id}
```

**Fraud config & events (admin)**
```
GET   /api/admin/fraud-config
PATCH /api/admin/fraud-config
GET   /api/admin/fraud-events
```

**Audit log (admin) — extended**
```
GET   /api/admin/audit-logs   now paginated + filterable (action, actor, target, date range, free-text)
```

**Enforcement (existing creation paths, extended):** the bulk/manual create
pipeline becomes: validate → **credit/balance check** (reject if exceeds
available credit, frozen, or user blocked; log rejection reason) → **rules
engine** (reject/flag on matching rule) → fraud scoring → **fraud auto-block**
(if score ≥ threshold: block tx, flag account, notify admins, write fraud_event)
→ persist with `balance_before` / `balance_after` → update account totals.
`login` rejects blocked users with their block reason.

---

## Phase 1 — frontend

- **Dashboard (user):** balance summary cards (current balance, credit limit,
  available credit), credit-utilization gauge, total spending/deposits, account
  status badge.
- **Status badge** component: Active / Suspended / Blocked / Under Review.
- **Admin → User Management:** per-user account panel with edit balance, add/
  remove funds, set credit limit, suspend credit, freeze, reset; block/unblock
  modal with reason picker + notes; status badges; rejection/auto-block history.
- **Admin → Transaction Rules:** create/edit/enable/disable/delete rules table.
- **Admin → Fraud Config:** threshold sliders + auto-block toggles; recent
  fraud-events feed.
- **Admin → Audit Log:** searchable, filterable, paginated table with before/
  after values.

---

## Phase 2 (summary)

Email service (`services/email.py`) with SMTP-or-console transport; 6-digit OTP
with expiry, resend, rate limiting, hashed token storage; `email_verifications`
collection. Registration issues a pending account → verify → activate. Login
gains an optional OTP step (per-user or admin-forced 2FA). `login_attempts`
collection stores history, IP, device, timestamp, success/failure. Admin can
force/disable 2FA and view login history.

## Phase 3 (summary)

Stripe/Mercury-style dashboard redesign: design-token CSS (light + dark themes
with a toggle), refreshed nav/cards/charts, animated widgets, balance & credit-
utilization widgets, recent-activity feed, live notifications. Final deliverables
docs: updated architecture diagram, full schema, API reference for every
endpoint, and a security review (authn/authz, rate limiting, OTP security, fraud
protection).

---

## Engineering guarantees

- Purely **additive** schema; existing CSV data, tokens, and the first
  expansion keep working with no migration.
- Every privileged action writes an **audit log** with before/after values.
- All pymongo calls run in `run_in_threadpool`; SSE stays responsive.
- Admin endpoints gated server-side via `get_current_admin`; ownership enforced
  on user-facing reads/writes.
- Backend must pass `python -m py_compile`; frontend must pass `vite build`
  before each phase is considered done.

# FraudDetect — API Reference

Base URL: `/` (all routes are prefixed `/api`). Interactive docs are available at
`/docs` (Swagger) and `/redoc` when the backend is running.

**Auth:** all protected endpoints require `Authorization: Bearer <JWT>`. Admin
endpoints additionally require the token's role to be `admin` (enforced
server-side). The SSE stream takes the token as a query param because the browser
`EventSource` API can't set headers.

Roles: **U** = any authenticated user, **A** = admin only, **P** = public.

---

## Authentication — `/api/auth`

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/register` | P | Create an **unverified** account; emails a 6-digit OTP. Returns `{requires_verification, email, dev_code?}` (no token yet). |
| POST | `/verify-email` | P | Body `{email, code}`. Verifies the OTP, marks the email verified, returns a `Token`. |
| POST | `/login` | P | Body `{email, password}`. On success returns a `Token`; if the account is unverified returns `{requires_verification}`; if 2FA is enforced returns `{requires_2fa}`; blocked accounts get `403`. Every attempt is logged. |
| POST | `/verify-2fa` | P | Body `{email, code}`. Verifies the login OTP, returns a `Token`. |
| POST | `/resend-otp` | P | Body `{email, purpose}` (`verify_email`\|`login_2fa`). Rate-limited resend. |
| GET | `/me` | U | Current user profile. |

`Token` = `{access_token, token_type, user}`. In dev mode (no SMTP) responses
include `dev_code` so the flow is testable without an email provider.

---

## Transactions — `/api/transactions`

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/upload-csv` | U | Upload a Kaggle-format CSV; scores with Isolation Forest, stores results, emits SSE + a fraud summary notification. |
| GET | `/dashboard` | U | Per-user dashboard stats (totals, approval/fraud rates). |
| GET | `/anomaly-score-distribution` | U | Histogram bins of anomaly scores (fraud vs legit). |
| GET | `/amount-vs-anomaly` | U | Scatter sample (amount vs anomaly score). |
| GET | `/transactions-over-time` | U | Time series of total + fraud counts. |
| GET | `/search` | U | Paginated search + filters + sort (scoped to the caller; admins see all). |
| GET | `/tags/options` | U | Canonical tag list. |
| GET | `/{txn_id}` | U | Full transaction detail (ownership enforced). |
| PATCH | `/{txn_id}/tags` | U | Update tag / category / description (ownership enforced). |

---

## Account & balance — `/api/account` (user) and `/api/admin` (admin)

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET | `/api/account/me` | U | Caller's balance summary (balance, credit limit, available credit, utilization, spending power, totals, status). |
| GET | `/api/account/me/history` | U | Caller's balance + credit-limit history. |
| GET | `/api/admin/users/{id}/account` | A | Full account + history for any user. |
| POST | `/api/admin/users/{id}/account/add-funds` | A | Body `{amount, note?}` — deposit into the user's balance. |
| POST | `/api/admin/users/{id}/account/remove-funds` | A | Withdraw from the user's balance. |
| PATCH | `/api/admin/users/{id}/account/balance` | A | Body `{balance, note?}` — set exact balance. |
| PATCH | `/api/admin/users/{id}/account/credit-limit` | A | Body `{credit_limit?` or `delta?, note?}` — set/adjust credit ceiling. |
| POST | `/api/admin/users/{id}/account/credit-suspend` | A | Body `{enabled, note?}` — suspend/resume the credit line. |
| POST | `/api/admin/users/{id}/account/freeze` | A | Body `{enabled, note?}` — freeze/unfreeze the balance. |
| POST | `/api/admin/users/{id}/account/reset` | A | Reset balance and drawn credit to zero. |

**Balance model:** `current_balance` is spendable cash; `credit_used` is drawn
credit; `available_credit = credit_limit − credit_used`; `spending_power =
balance + available_credit`. A purchase draws cash first, then credit.

---

## User blocking & status — `/api/admin`

| Method | Path | Role | Description |
|--------|------|------|-------------|
| POST | `/users/{id}/block` | A | Body `{reason_code, reason?, notes?}`. Blocks login + transactions. |
| POST | `/users/{id}/unblock` | A | Body `{notes?}`. Restores to active. |
| PATCH | `/users/{id}/status` | A | Body `{status, notes?}` (`active`\|`suspended`\|`under_review`). |
| GET | `/users/{id}/status-history` | A | Block/unblock/status history. |
| PATCH | `/users/{id}/2fa` | A | Body `{enabled}` — force/disable 2FA. |
| GET | `/users/{id}/login-history` | A | Recent login attempts (IP, device, outcome). |

`reason_code` ∈ `fraud · suspicious_activity · manual_review · account_violation · custom`.

---

## Admin user management & transactions — `/api/admin`

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET | `/users` | A | List users + summary stats (tx, fraud, status, balances). `?search=`. |
| GET | `/users/{id}` | A | Single user summary. |
| GET | `/users/{id}/transactions` | A | Paginated, filterable transaction history. |
| GET | `/users/{id}/analytics` | A | Risk score, spending-by-tag, volume, time trend. |
| POST | `/transactions/bulk` | A | Create one/many transactions for a user (full enforcement pipeline). |
| GET | `/audit-logs` | A | Recent audit entries (simple). |
| GET | `/audit-logs/search` | A | Searchable, paginated, filterable audit log. |

Analytics dashboards (`/api/admin/analytics`, `/confusion-matrix`,
`/fraud-rate-trend`, `/fraud-rates-by-user`, `/amount-distribution`,
`/global-anomaly-distribution`, `/v-feature-boxplots`) are admin-only.

---

## Transaction rules & fraud config — `/api/admin`

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET | `/transaction-rules` | A | List rules. |
| POST | `/transaction-rules` | A | Create a rule (`merchant`\|`category`\|`amount_range`\|`country`\|`card_type`\|`user`; action `block`\|`flag`). |
| PATCH | `/transaction-rules/{id}` | A | Update a rule. |
| POST | `/transaction-rules/{id}/toggle` | A | Enable/disable a rule. |
| DELETE | `/transaction-rules/{id}` | A | Delete a rule. |
| GET | `/fraud-config` | A | Current auto-block/flag thresholds + toggles. |
| PATCH | `/fraud-config` | A | Update thresholds (`auto_block_threshold`, `auto_flag_threshold`, `flag_account_on_block`, `notify_admins`). |
| GET | `/fraud-events` | A | Recent auto-block / auto-flag events. |

---

## Notifications & real-time

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET | `/api/notifications` | U | Recent notifications + unread count. |
| POST | `/api/notifications/mark-read` | U | Body `{notification_ids?}` (null = all). |
| GET | `/api/stream?token=<jwt>` | U | Server-Sent Events: `connected`, `notification`, `transactions_updated`, keepalives. |

---

## Common error shapes

- `400` validation / bad input — `{"detail": "<message>"}` or a list of field errors.
- `401` missing/invalid token. `403` insufficient role, blocked account.
- `404` not found. `429` OTP rate-limited.

All list endpoints that paginate return `{items, total, page, page_size, total_pages}`.

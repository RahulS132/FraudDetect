# FraudDetect — Security Review

This document covers the authentication, authorization, rate-limiting, OTP, and
fraud-protection posture of the platform, plus known limitations and hardening
recommendations for production.

## Authentication

- **Passwords** are hashed with **bcrypt** (`auth.get_password_hash` /
  `verify_password`). Input is truncated to bcrypt's 72-byte limit consistently
  on both hash and verify so the two never diverge. Plaintext passwords are never
  stored or logged.
- **Tokens** are **JWT (HS256)** signed with `SECRET_KEY`. The token carries
  `sub` (email), `id`, and `role` so hot-path handlers authorize without a DB
  round-trip. `get_full_current_user` is used only where profile fields are
  needed.
- **Email verification**: new accounts are created **unverified** and cannot
  obtain a token until a 6-digit OTP is confirmed. Legacy accounts (no
  `email_verified` field) are treated as verified for backward compatibility.
- **Two-factor authentication**: when an admin enforces 2FA (`force_2fa`), login
  requires an emailed OTP before a token is issued.

**Recommendations for production:** set a strong 32+ char `SECRET_KEY` from a
secret manager; shorten `ACCESS_TOKEN_EXPIRE_MINUTES` (currently 30 days) and add
refresh tokens; consider token revocation/rotation on password change or block.

## Authorization

- Every protected route depends on `get_current_user`; every admin route depends
  on `get_current_admin`, which checks the role claim server-side — the frontend
  route guard is convenience only and is never trusted.
- **Ownership enforcement**: non-admin reads/writes are scoped by `user_id`. The
  search service filters by the caller; transaction detail and tag updates
  re-check ownership before returning or writing.
- Admins cannot block their own account, change their own status, or block other
  admins (guards in `blocking` service + routes).

## Rate limiting & abuse protection

- **OTP**: resend is throttled (`OTP_RESEND_WINDOW_SECONDS`, default 60s);
  verification attempts are capped per code (`OTP_MAX_ATTEMPTS`, default 5); codes
  expire (`OTP_EXP_MINUTES`, default 10) and are deleted by a MongoDB TTL index.
- **Login attempts** are recorded (success/failure, IP, device) for audit and
  anomaly review.
- **Recommendation:** add a per-IP edge rate-limiter (e.g. a middleware or
  Redis token bucket) on `/api/auth/*` to blunt credential-stuffing, since the
  in-app throttle is per-email, not per-IP.

## OTP security

- Codes are random 6-digit values (`secrets.randbelow`) stored **hashed**
  (SHA-256) — the plaintext code is never persisted. Issuing a new code
  invalidates prior unused codes for the same purpose. The dev-mode echo
  (`dev_code`) is returned **only** when SMTP is unconfigured and `OTP_DEV_ECHO`
  is on; disable it in production by configuring SMTP.

## Input validation & injection safety

- **Pydantic** validates every request body — amount bounds, enum membership
  (tags, statuses, rule types, reason codes), string-length caps, batch size
  (1–1000), and regex-constrained query params (`sort_by`, `sort_dir`,
  `fraud_status`).
- **Regex/ReDoS**: user-supplied search text is escaped with `re.escape` before
  use in Mongo `$regex`. Object ids are validated before use.
- **NoSQL injection**: queries use structured pymongo filters, not string
  concatenation; user input never becomes a query operator.

## Fraud protection

- **Two scoring paths**: Isolation Forest (CSV) and a transparent rule-based
  scorer (manual). Manual scores map onto the same scale the charts use.
- **Rules engine** evaluates admin-defined block/flag rules before a transaction
  posts; the first `block` match rejects it and the rejection is audited.
- **Auto-blocking**: scores ≥ `auto_block_threshold` block the transaction, write
  a `fraud_event`, optionally move the account to **under review**, and notify all
  admins in real time. Scores ≥ `auto_flag_threshold` flag for review.
- **Credit/balance enforcement**: transactions that exceed spending power, or hit
  a frozen account, are rejected with a logged reason — preventing over-limit
  spend.

## Auditability

- Every privileged, state-changing admin action (block/unblock, status change,
  balance add/remove/set, credit-limit change, freeze/suspend/reset, fraud-config
  change, rule CRUD, bulk create, 2FA toggle) is written to `audit_logs` with the
  actor, target, **before/after values**, and timestamp, and is searchable from
  the admin Audit Log page.

## Transport & secrets

- Secrets (`MONGODB_URL`, `SECRET_KEY`, SMTP creds) live in `backend/.env`, which
  is git-ignored. Nothing that reveals them is logged.
- MongoDB Atlas connections use TLS (certifi CA bundle).
- **Production:** terminate TLS at the edge, restrict CORS `ALLOWED_ORIGINS` to
  the real frontend origin, and run behind a firewall with the Atlas IP allowlist
  locked to the server.

## Known limitations / future hardening

1. JWTs are long-lived and not revocable — add refresh + rotation.
2. In-app OTP/login throttling is per-email; add per-IP edge limiting.
3. The event broker is in-process (single instance) — move to Redis pub/sub for
   multi-replica deployments.
4. No CSRF token (the app is token-in-header, not cookie-based, so CSRF risk is
   low) — keep tokens out of cookies to preserve this property.
5. Consider account lockout after N failed logins (data is already captured in
   `login_attempts`).

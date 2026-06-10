# FraudDetect — Architecture

## Overview

FraudDetect is a credit-card fraud-detection and transaction-management platform.
A React/Vite single-page app talks to a FastAPI backend over REST; FastAPI
persists to MongoDB Atlas and pushes live updates to browsers over Server-Sent
Events. Two fraud engines score transactions: an **Isolation Forest** for
uploaded Kaggle-format CSVs and a transparent **rule-based scorer** for
hand-entered/admin transactions. A pluggable email service delivers OTPs for
email verification and login 2FA.

```
                         ┌──────────────────────────────────────────────────┐
   ┌──────────────┐      │  FastAPI (uvicorn)                                │
   │  React SPA   │      │                                                  │
   │  (Vite)      │─REST─▶│  routes/                                         │
   │              │      │    auth · transactions · search · admin ·         │
   │  ┌────────┐  │      │    admin_tx · account · rules · notifications     │
   │  │Theme   │  │◀─SSE─│  services/                                        │
   │  │Realtime│  │      │    events(EventBroker) · notifications · audit ·  │
   │  │Auth    │  │      │    search · account · blocking · rules_engine ·   │
   │  │Toast   │  │      │    fraud_config · email · otp · security_log      │
   │  └────────┘  │      │  fraud_detection (IsolationForest + RuleScorer)   │
   └──────────────┘      └───────┬───────────────────────────┬──────────────┘
          ▲                      │                           │
          │                MongoDB Atlas               SMTP (pluggable;
          │         ┌───────────────────────────┐      dev = console log)
          │         │ users · transactions ·    │
          │         │ detection_results ·       │
          │         │ notifications · audit_logs│
          │         │ transaction_rules ·       │
          │         │ fraud_config · fraud_events│
          │         │ account_events ·          │
          │         │ user_status_events ·      │
          │         │ email_verifications ·     │
          │         │ login_attempts            │
          │         └───────────────────────────┘
          └──── EventBroker fans fraud alerts + data-change events to the
                affected user's tabs and to all admin tabs (in-process pub/sub)
```

## Components

### Frontend (`frontend/`)
- **React 18 + Vite 7**, React Router, Chart.js / react-chartjs-2, axios, lucide-react.
- **Contexts**: `AuthProvider` (JWT + verify/2FA challenge flow), `RealtimeProvider`
  (single SSE connection + polling fallback), `ToastProvider`, `ThemeProvider`
  (light/dark, persisted, retints Chart.js).
- **Shared components**: `Sidebar`, `TopBar`, `NotificationCenter`,
  `TransactionsExplorer`, `TransactionDetailDrawer`, `BalanceWidgets`,
  `AdminAccountPanel`, `StatusBadge`, `OtpForm`.
- **Pages**: Login, Register, Dashboard, Transactions, UploadCSV, AdminAnalytics,
  AdminUsers, AdminTransactions, TransactionRules, FraudConfig, AuditLog.

### Backend (`backend/`)
- **FastAPI** with a thin route layer over a **services layer** that holds all
  business logic. Every pymongo call runs in `run_in_threadpool` so the event
  loop (and SSE streams) stay responsive.
- **Auth**: JWT (HS256) bearer tokens; bcrypt password hashing; role claims
  baked into the token to avoid per-request DB lookups on hot paths.
- **Fraud engine**: `fraud_detection.py` — Isolation Forest for CSV uploads;
  `RuleBasedFraudScorer` (amount/category/time/velocity → 0–100 score) for manual
  transactions, mapped onto the same anomaly-score scale the charts read.
- **Real-time**: `services/events.py` `EventBroker` — in-process async pub/sub
  keyed by `user_id` or the `__admins__` sentinel; documented swap-point for Redis
  to scale horizontally.

### Data store
MongoDB Atlas (M0+). Twelve collections (see `docs/DATABASE_SCHEMA.md`). All
second-expansion changes are additive and backward-compatible.

### Email
`services/email.py` sends over SMTP when configured, otherwise logs the message
(and OTP) to the console in dev mode. `services/otp.py` issues hashed, expiring,
rate-limited 6-digit codes.

## Request lifecycle — transaction creation (with enforcement)

```
admin submits transaction(s)
        │
        ▼
 block check (target user active?) ──no──▶ 403 rejected
        │ yes
        ▼
 for each transaction:
   rules engine ──block match──▶ rejected + audited
        │ pass / flag
        ▼
   fraud score (rule scorer) ──≥ auto-block threshold──▶ block + flag account + fraud_event + notify admins
        │ below
        ▼
   balance / credit check ──exceeds spending power──▶ rejected + reason logged
        │ ok (cash first, then credit)
        ▼
   persist txn (+ detection_result) with balance_before / balance_after
        │
        ▼
 commit balance deltas · audit log · SSE "transactions_updated" · fraud notifications
```

## Why SSE (not WebSockets)
The app only needs server→client push (live dashboards, notifications, balance
updates). SSE is one-directional, rides plain HTTP through the existing proxy,
auto-reconnects natively, and adds no dependency. The client falls back to
polling if the stream drops.

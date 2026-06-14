# FraudDetect

Credit-card fraud detection and transaction-management platform built on FastAPI, React, and MongoDB. An Isolation Forest model scores uploaded transactions while a per-account statistical engine scores manual ones, on top of a full account system — balances, credit limits, user blocking, configurable fraud rules, email verification, and 2FA.

[![Python](https://img.shields.io/badge/Python-3.13.1-blue.svg)](https://www.python.org/downloads/)
[![Node](https://img.shields.io/badge/Node-22-339933.svg)](https://nodejs.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Overview

Users upload a CSV of transactions (Kaggle credit-card format), the backend runs an Isolation Forest over each row, and the results are persisted to MongoDB. Admins can also create real-world transactions by hand — these flow through a transparent, per-account fraud scorer, a rules engine, and live balance/credit enforcement. The React frontend renders user-scoped dashboards (with live balances and a credit-utilization gauge) and global admin analytics, in both light and dark themes.

## Features

### Fraud detection
- Anomaly detection with scikit-learn's **Isolation Forest** for uploaded CSVs
- **Per-account statistical scorer** for manual transactions — flags amounts that are statistical outliers for that account (z-score), plus velocity, category, time-of-day, and absolute-amount signals
- **Configurable fraud auto-blocking** — set score thresholds; transactions over the limit are auto-blocked, the account is flagged for review, and admins are notified
- **Transaction rules engine** — block or flag transactions by merchant, category, amount range, country, card type, or specific user

### Accounts & money
- **Balance & credit system** — each account has a spendable balance, credit limit, drawn credit, available credit, and spending power
- **Bank-card transaction flow** — transactions move money **in** (deposits, refunds) and **out** (purchases, withdrawals); balances update accordingly, drawing on credit when cash runs out
- **Monthly credit-utilization** gauge that resets each calendar month
- **Admin account controls** — add/remove funds, set balance, set/suspend credit limit, freeze, reset, all with before/after history
- **Credit-limit enforcement** — transactions that exceed available funds are rejected with a logged reason (a credit limit of 0 means "no limit")

### Access & security
- **Email verification** — new accounts confirm a 6-digit OTP (hashed, expiring, rate-limited) before activation
- **Two-factor authentication** — admins can force email-OTP 2FA on login per user
- **Login history** — every attempt recorded with IP, device, and outcome
- **User blocking & status** — block (with reason), suspend, or mark under review; blocked users can't log in or transact; status badges throughout
- **Security audit log** — every privileged admin action recorded with actor, target, and before/after values; searchable admin page
- JWT authentication with role-based access (user / admin) and per-user data isolation

### Experience
- **Real-time updates** — dashboards, charts, balances, and summary cards refresh live via Server-Sent Events (no page reload), with a polling fallback
- **Live fraud notifications** — flagged transactions push real-time alerts (one summary per batch) to the affected user and all admins; notification center with unread/read state, severity, and persisted history
- **Light & dark mode** — full theme with a sidebar toggle; respects your OS preference and persists
- **Searchable transactions** — search/filter/sort by id, user, amount, date, category, description, tags, and fraud status (users see their own; admins see all)
- **Transaction tags** — Food, Rent, Salary, Utilities, Entertainment, Investment, Travel, Insurance; assignable and editable
- **Clickable transaction details** — every row opens a drawer with full detail and inline editing
- **Admin transaction management** — create transactions for any user individually or in bulk (incl. money-in/out type)
- **Per-user admin views** — risk score, fraud history, transaction volume, spending analytics, account panel, and login history
- CSV ingestion with the standard Kaggle credit-card schema


## Quick start

The repo pins Python, Node, and all dependency versions so the project runs identically on every machine. Use the version managers below — bypassing them is what causes "works on my machine" issues.

### Prerequisites

Install once per machine.

- **pyenv** — [macOS / Linux](https://github.com/pyenv/pyenv) (`brew install pyenv`) or [pyenv-win](https://github.com/pyenv-win/pyenv-win)
- **nvm** — [macOS / Linux](https://github.com/nvm-sh/nvm) or [nvm-windows](https://github.com/coreybutler/nvm-windows)
- **MongoDB** — a local instance or a MongoDB Atlas account (free tier)

### Setup

```bash
git clone https://github.com/RahulS132/FraudDetect.git
cd FraudDetect

# Python — pyenv reads .python-version automatically
# Windows / pyenv-win users: if `pyenv update` fails in PowerShell, use the already-installed Python 3.13.1 and continue with the venv step.
pyenv install 3.13.1
python -m venv .venv
source .venv/bin/activate                          # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip                # Windows: python.exe -m pip install --upgrade pip
pip install -r backend/requirements.txt

# Node — pass the version explicitly so it works on both nvm (macOS/Linux)
# and nvm-windows (which doesn't auto-read .nvmrc).
cd frontend
nvm install 20.18.0
nvm use 22
npm ci
cd ..
```

Create `backend/.env` using the keys listed under [Environment variables](#environment-variables).

### Run

In two terminals:

```bash
# Terminal 1 — backend
source .venv/bin/activate
cd backend
python main.py
```

```bash
# Terminal 2 — frontend
cd frontend
nvm use 22
npm run dev
```

| Service          | URL                              |
| ---------------- | -------------------------------- |
| Frontend         | http://localhost:3000            |
| Backend API      | http://localhost:8000            |
| Interactive docs | http://localhost:8000/docs       |

### Troubleshooting

- **`pyenv: command not found`** — finish pyenv's shell-setup step (add the snippet to `~/.zshrc` or `~/.bashrc`), then open a new terminal.
- **`pyenv-install: definition not found: 3.13.1`** — on Windows, this usually means pyenv-win is stale or its updater is unhappy in PowerShell (`htmlfile: This command is not supported`). Open Command Prompt and retry `pyenv update`, or skip pyenv entirely if `python --version` already reports 3.13.1 inside your venv.
- **`python --version` shows the wrong version** — confirm `.python-version` exists in the project root, then run `pyenv rehash`.
- **`nvm: command not found`** — same idea; source nvm in your shell rc file.
- **`npm ci` complains about engines / `vite` won't start** — you're on an old Node. Vite 7 needs Node 20.19+ or 22.12+. Run `nvm install 22 && nvm use 22` from `frontend/`.
- **`Cannot find module .../frontend/dev`** — you ran `nvm run dev`. Use `npm run dev` instead (`nvm` only switches Node versions; `npm` runs the scripts).
- **`Cannot find module @rollup/rollup-darwin-arm64`** — npm's optional-deps bug. Delete `node_modules` and `package-lock.json`, then `npm install` (or `npm ci`).
- **`bcrypt` errors on import** — stale venv. Reset it: `rm -rf .venv && python -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt`.
- **A package fails to install on Python 3.13** — confirm `python --version` reads `3.13.1`, not 3.12 or 3.14.

## Architecture

The React frontend talks to FastAPI over REST and receives live updates over Server-Sent Events. FastAPI persists everything to MongoDB (Atlas in production, local in dev) and holds the business logic in a services layer (events broker, notifications, audit, search, account, blocking, rules engine, fraud config, email/OTP). The Isolation Forest model is fit per-upload on the incoming CSV; manual transactions are scored by a transparent per-account rule scorer. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full diagram.

## Project structure

```
FraudDetect/
├── backend/
│   ├── main.py              FastAPI entry point
│   ├── config.py            Settings (pydantic-settings)
│   ├── database.py          MongoDB connection and collections
│   ├── models.py            Pydantic models
│   ├── auth.py              JWT and password hashing
│   ├── fraud_detection.py   Isolation Forest + per-account rule scorer
│   ├── routes/              auth, transactions, search, admin, account, rules, notifications
│   └── services/            events (SSE broker), notifications, audit, search,
│                            account, blocking, rules_engine, fraud_config, email, otp
├── frontend/
│   ├── src/
│   │   ├── components/      Shared components (TopBar, NotificationCenter, BalanceWidgets, …)
│   │   ├── contexts/        Auth, Realtime (SSE), Toast, Theme (light/dark)
│   │   ├── pages/           Dashboard, Transactions, AdminUsers, TransactionRules, FraudConfig, AuditLog, …
│   │   ├── theme.css        Design tokens + dark mode
│   │   └── App.jsx
│   └── package.json
├── docs/                    ARCHITECTURE.md, API_REFERENCE.md, SECURITY_REVIEW.md
├── sample_data.csv          Example dataset (Kaggle columns only)
└── sample_data_au.csv       Example dataset with Australian merchants + tags
```

## Tech stack

**Backend** — FastAPI, MongoDB (Atlas), scikit-learn, pandas, python-jose, bcrypt, Server-Sent Events, SMTP (email OTP)

**Frontend** — React 18, Vite 7, React Router, Chart.js, Axios, lucide-react

## Dataset

Compatible with the [Kaggle Credit Card Fraud Detection Dataset](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud).

Expected columns: `Time`, `V1`–`V28`, `Amount`, `Class` (0 = legitimate, 1 = fraud).

## API

```
# Authentication & verification
POST   /api/auth/register            # creates an unverified account, emails an OTP
POST   /api/auth/verify-email        # confirm OTP → returns a token
POST   /api/auth/login               # may return a 2FA / verification challenge
POST   /api/auth/verify-2fa          # confirm login OTP → returns a token
POST   /api/auth/resend-otp
GET    /api/auth/me

# Transactions (user-scoped)
POST   /api/transactions/upload-csv
GET    /api/transactions/dashboard
GET    /api/transactions/anomaly-score-distribution
GET    /api/transactions/amount-vs-anomaly
GET    /api/transactions/transactions-over-time

# Transactions — search & detail (auto-scoped: users see own, admins see all)
GET    /api/transactions/search
GET    /api/transactions/tags/options
GET    /api/transactions/{txn_id}
PATCH  /api/transactions/{txn_id}/tags

# Notifications & real-time
GET    /api/notifications
POST   /api/notifications/mark-read
GET    /api/stream?token=<jwt>          # Server-Sent Events

# Admin (admin role required)
GET    /api/admin/analytics
GET    /api/admin/fraud-rates-by-user
GET    /api/admin/global-anomaly-distribution
GET    /api/admin/fraud-rate-trend
GET    /api/admin/v-feature-boxplots
GET    /api/admin/confusion-matrix
GET    /api/admin/amount-distribution

# Account & balance (user)
GET    /api/account/me                   # balance, credit, utilization, totals
GET    /api/account/me/history

# Admin — transaction management & per-user views
GET    /api/admin/users
GET    /api/admin/users/{user_id}
GET    /api/admin/users/{user_id}/transactions
GET    /api/admin/users/{user_id}/analytics
POST   /api/admin/transactions/bulk
GET    /api/admin/audit-logs
GET    /api/admin/audit-logs/search

# Admin — account, credit & blocking
GET    /api/admin/users/{id}/account
POST   /api/admin/users/{id}/account/add-funds | remove-funds | freeze | reset | credit-suspend
PATCH  /api/admin/users/{id}/account/balance | credit-limit
POST   /api/admin/users/{id}/block | unblock
PATCH  /api/admin/users/{id}/status
GET    /api/admin/users/{id}/status-history
PATCH  /api/admin/users/{id}/2fa
GET    /api/admin/users/{id}/login-history

# Admin — rules & fraud config
GET    /api/admin/transaction-rules
POST   /api/admin/transaction-rules
PATCH  /api/admin/transaction-rules/{id}
POST   /api/admin/transaction-rules/{id}/toggle
DELETE /api/admin/transaction-rules/{id}
GET    /api/admin/fraud-config
PATCH  /api/admin/fraud-config
GET    /api/admin/fraud-events
```

Full interactive documentation is generated at `/docs`. A complete endpoint reference lives in [docs/API_REFERENCE.md](docs/API_REFERENCE.md).

## Environment variables

Create `backend/.env`:

```env
# MongoDB
MONGODB_URL=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/
DATABASE_NAME=frauddetect

# JWT
SECRET_KEY=<at-least-32-character-secret>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=43200

# CORS
ALLOWED_ORIGINS=["http://localhost:3000"]

# Email (optional) — for verification + 2FA codes.
# Leave SMTP_USER/SMTP_PASSWORD blank to run in dev mode: codes are printed to
# the backend console (and returned in the API response) instead of emailed.
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
```

Any SMTP provider works (Brevo, SendGrid, Mailgun, Gmail, …). With no SMTP configured, email verification and 2FA still work end-to-end in dev mode using the console/echoed code.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components, diagram, and request lifecycle
- [docs/API_REFERENCE.md](docs/API_REFERENCE.md) — every endpoint, grouped by area
- [docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md) — auth, OTP, rate limiting, fraud protection
- [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) — all MongoDB collections and fields

## Deployment

The frontend deploys cleanly to Vercel. The FastAPI backend is better suited to Railway, Render, or Fly.io than Vercel's serverless Python runtime. MongoDB runs on Atlas. Set the environment variables above on your host, and ensure the platform's idle timeout is above the SSE keepalive (20s).

## License

MIT — see [LICENSE](LICENSE).

## Maintainer

Rahul Sigdel — [@RahulS132](https://github.com/RahulS132)

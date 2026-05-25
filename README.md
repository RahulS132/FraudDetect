# FraudDetect

Credit-card fraud detection built on FastAPI, React, and MongoDB. An Isolation Forest model scores uploaded transactions for anomaly, with per-user dashboards and admin-level analytics across the dataset.

[![Python](https://img.shields.io/badge/Python-3.13.1-blue.svg)](https://www.python.org/downloads/)
[![Node](https://img.shields.io/badge/Node-20.18.0-339933.svg)](https://nodejs.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## Overview

Users upload a CSV of transactions (Kaggle credit-card format), the backend runs an Isolation Forest over each row, and the results are persisted to MongoDB. The React frontend renders user-scoped dashboards with Chart.js. Admins get global analytics across every user.

## Features

- Anomaly detection with scikit-learn's Isolation Forest
- Interactive dashboards backed by Chart.js
- JWT authentication with role-based access (user / admin)
- Per-user data isolation; admin role for global views
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
pyenv install 3.13.1
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r backend/requirements.txt

# Node — nvm reads .nvmrc automatically
cd frontend
nvm install
nvm use
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
nvm use
npm run dev
```

| Service          | URL                              |
| ---------------- | -------------------------------- |
| Frontend         | http://localhost:3000            |
| Backend API      | http://localhost:8000            |
| Interactive docs | http://localhost:8000/docs       |

### Troubleshooting

- **`pyenv: command not found`** — finish pyenv's shell-setup step (add the snippet to `~/.zshrc` or `~/.bashrc`), then open a new terminal.
- **`python --version` shows the wrong version** — confirm `.python-version` exists in the project root, then run `pyenv rehash`.
- **`nvm: command not found`** — same idea; source nvm in your shell rc file.
- **`npm ci` complains about engines** — you're not on Node 20.x. Run `nvm use` from `frontend/`.
- **`bcrypt` errors on import** — stale venv. Reset it: `rm -rf .venv && python -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt`.
- **A package fails to install on Python 3.13** — confirm `python --version` reads `3.13.1`, not 3.12 or 3.14.

## Architecture

The React frontend talks to FastAPI over REST. FastAPI persists everything to MongoDB (Atlas in production, local in dev). The Isolation Forest model lives inside the backend and is fit per-upload on the incoming CSV; scored rows are written back to MongoDB and served to the dashboard endpoints.

## Project structure

```
FraudDetect/
├── backend/
│   ├── main.py              FastAPI entry point
│   ├── config.py            Settings (pydantic-settings)
│   ├── database.py          MongoDB connection and collections
│   ├── models.py            Pydantic models
│   ├── auth.py              JWT and password hashing
│   ├── fraud_detection.py   Isolation Forest pipeline
│   └── routes/              Auth, transaction, and admin endpoints
├── frontend/
│   ├── src/
│   │   ├── components/      Shared React components
│   │   ├── pages/           Dashboard, login, register, etc.
│   │   └── App.jsx
│   └── package.json
└── sample_data.csv          Example dataset
```

## Tech stack

**Backend** — FastAPI, MongoDB (Atlas), scikit-learn, pandas, python-jose, bcrypt

**Frontend** — React 18, Vite, React Router, Chart.js, Axios

## Dataset

Compatible with the [Kaggle Credit Card Fraud Detection Dataset](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud).

Expected columns: `Time`, `V1`–`V28`, `Amount`, `Class` (0 = legitimate, 1 = fraud).

## API

```
# Authentication
POST   /api/auth/register
POST   /api/auth/login
GET    /api/auth/me

# Transactions (user-scoped)
POST   /api/transactions/upload-csv
GET    /api/transactions/dashboard
GET    /api/transactions/anomaly-score-distribution
GET    /api/transactions/amount-vs-anomaly
GET    /api/transactions/transactions-over-time

# Admin (admin role required)
GET    /api/admin/analytics
GET    /api/admin/fraud-rates-by-user
GET    /api/admin/global-anomaly-distribution
GET    /api/admin/fraud-rate-trend
GET    /api/admin/v-feature-boxplots
GET    /api/admin/confusion-matrix
GET    /api/admin/amount-distribution
```

Full interactive documentation is generated at `/docs`.

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
```

## Deployment

The frontend deploys cleanly to Vercel. The FastAPI backend is better suited to Railway, Render, or Fly.io than Vercel's serverless Python runtime. MongoDB runs on Atlas. See [DEPLOYMENT.md](DEPLOYMENT.md) for the full procedure.

## License

MIT — see [LICENSE](LICENSE).

## Maintainer

Rahul Sigdel — [@RahulS132](https://github.com/RahulS132)

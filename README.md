# 🛡️ FraudDetect

> AI-powered credit card fraud detection system with real-time analytics

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![React](https://img.shields.io/badge/React-18.2-61dafb.svg)](https://reactjs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688.svg)](https://fastapi.tiangolo.com/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-47A248.svg)](https://www.mongodb.com/cloud/atlas)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 📋 Overview

FraudDetect is a production-ready, full-stack web application that uses machine learning to detect fraudulent credit card transactions. Built with FastAPI, React, and MongoDB, it provides real-time fraud detection, interactive dashboards, and comprehensive analytics.

### ✨ Key Features

- 🤖 **ML-Powered Detection** - Isolation Forest algorithm for anomaly detection
- 📊 **Interactive Dashboards** - Real-time statistics with Chart.js visualizations
- 👥 **Multi-User Support** - Secure authentication with role-based access control
- 🔐 **Enterprise Security** - JWT authentication, password hashing, data isolation
- 📈 **Admin Analytics** - Global fraud statistics across all users
- 🎨 **Modern UI** - Responsive design with gradient aesthetics

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB Atlas

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/RahulS132/FraudDetect.git
cd FraudDetect
```

2. **Set up the backend**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env with your MongoDB credentials
```

4. **Set up the frontend**
```bash
cd frontend
npm install
```

5. **Run the application**

Terminal 1 (Backend):
```bash
cd backend
python main.py
```

Terminal 2 (Frontend):
```bash
cd frontend
npm run dev
```

6. **Access the application**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## 📊 Dataset

Compatible with the [Kaggle Credit Card Fraud Detection Dataset](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud)

**Expected Format:**
- Columns: Time, V1-V28, Amount, Class
- Class: 0 = Legitimate, 1 = Fraud

## 🏗️ Architecture

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   React     │ ───► │   FastAPI   │ ───► │  MongoDB    │
│  Frontend   │      │   Backend   │      │   Atlas     │
└─────────────┘      └─────────────┘      └─────────────┘
       │                    │
       │              ┌─────▼─────┐
       │              │ Isolation │
       │              │  Forest   │
       │              └───────────┘
       │
   Chart.js
```

## 🛠️ Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **MongoDB** - NoSQL database with Atlas
- **scikit-learn** - Machine learning (Isolation Forest)
- **pandas** - Data processing
- **JWT** - Secure authentication
- **bcrypt** - Password hashing

### Frontend
- **React 18** - UI library
- **Vite** - Build tool
- **React Router** - Client-side routing
- **Chart.js** - Data visualization
- **Axios** - HTTP client

## 📁 Project Structure

```
frauddetect/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration
│   ├── database.py          # MongoDB connection
│   ├── models.py            # Pydantic models
│   ├── auth.py              # Authentication
│   ├── fraud_detection.py   # ML algorithm
│   └── routes/              # API endpoints
├── frontend/
│   ├── src/
│   │   ├── components/      # React components
│   │   ├── contexts/        # React contexts
│   │   ├── pages/           # Page components
│   │   └── App.jsx          # Main app
│   └── package.json
└── sample_data.csv          # Example dataset
```

## 🔐 Security Features

- ✅ JWT token authentication
- ✅ Password hashing with bcrypt
- ✅ Role-based access control (User/Admin)
- ✅ Data isolation per user
- ✅ CORS configuration
- ✅ Input validation with Pydantic
- ✅ Environment variable protection

## 🎯 User Roles

### User
- Upload CSV files
- View personal dashboard
- See fraud detection statistics
- Access transaction analytics

### Admin
- View global analytics
- Monitor all users' statistics
- Track fraud rates by user
- Access system-wide metrics

## 📈 Machine Learning

**Algorithm:** Isolation Forest (Unsupervised Anomaly Detection)

**Detection Logic:**
```python
if (anomaly_detected OR Class == 1):
    is_fraud = True
    is_approved = False
else:
    is_fraud = False
    is_approved = True
```

**Features:**
- Contamination: 0.1 (10% expected fraud)
- Features: V1-V28, Time, Amount (standardized)
- Real-time processing and classification

## 🚀 Deployment

### Vercel + MongoDB Atlas

1. **Backend:** Deploy to Vercel Serverless Functions
2. **Frontend:** Deploy to Vercel Static Hosting
3. **Database:** MongoDB Atlas (Free tier available)

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions.

## 📖 API Endpoints

### Authentication
```
POST   /api/auth/register      # Register new user
POST   /api/auth/login         # Login user
GET    /api/auth/me            # Get current user
```

### Transactions
```
POST   /api/transactions/upload-csv     # Upload and process CSV
GET    /api/transactions/dashboard      # Get user statistics
```

### Admin (Admin Only)
```
GET    /api/admin/analytics              # Global analytics
GET    /api/admin/fraud-rates-by-user   # Fraud rates by user
```

## 🧪 Testing

1. **Register a user account**
2. **Upload sample_data.csv**
3. **View dashboard statistics**
4. **Create admin user** (see documentation)
5. **Access admin analytics**

## 📝 Environment Variables

```env
# MongoDB
MONGODB_URL=mongodb+srv://username:password@cluster.mongodb.net/
DATABASE_NAME=frauddetect

# JWT
SECRET_KEY=your-secret-key-min-32-characters
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=43200

# CORS
ALLOWED_ORIGINS=["http://localhost:3000"]
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📧 Contact

Rahul Sigdel - [@RahulS132](https://github.com/RahulS132)

Project Link: [https://github.com/RahulS132/FraudDetect](https://github.com/RahulS132/FraudDetect)

---

<p align="center">Made with ❤️ for secure financial transactions</p>

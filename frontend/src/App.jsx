import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ToastProvider } from './contexts/ToastContext';
import { RealtimeProvider } from './contexts/RealtimeContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Login } from './pages/Login';
import { Register } from './pages/Register';
import { Dashboard } from './pages/Dashboard';
import { UploadCSV } from './pages/UploadCSV';
import { AdminAnalytics } from './pages/AdminAnalytics';
import { Transactions } from './pages/Transactions';
import { AdminTransactions } from './pages/AdminTransactions';
import { AdminUsers } from './pages/AdminUsers';
import { TransactionRules } from './pages/TransactionRules';
import { FraudConfig } from './pages/FraudConfig';
import { AuditLog } from './pages/AuditLog';

function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthProvider>
          <RealtimeProvider>
            <Router>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />

              <Route
                path="/dashboard"
                element={
                  <ProtectedRoute>
                    <Dashboard />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/transactions"
                element={
                  <ProtectedRoute>
                    <Transactions />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/upload"
                element={
                  <ProtectedRoute>
                    <UploadCSV />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/admin"
                element={
                  <ProtectedRoute adminOnly={true}>
                    <AdminAnalytics />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/admin/transactions"
                element={
                  <ProtectedRoute adminOnly={true}>
                    <AdminTransactions />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/admin/users"
                element={
                  <ProtectedRoute adminOnly={true}>
                    <AdminUsers />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/admin/rules"
                element={
                  <ProtectedRoute adminOnly={true}>
                    <TransactionRules />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/admin/fraud-config"
                element={
                  <ProtectedRoute adminOnly={true}>
                    <FraudConfig />
                  </ProtectedRoute>
                }
              />

              <Route
                path="/admin/audit-log"
                element={
                  <ProtectedRoute adminOnly={true}>
                    <AuditLog />
                  </ProtectedRoute>
                }
              />

              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
            </Router>
          </RealtimeProvider>
        </AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}

export default App;

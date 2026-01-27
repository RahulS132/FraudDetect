import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Doughnut, Bar } from 'react-chartjs-2';
import { Chart as ChartJS, ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement, Title } from 'chart.js';
import { TrendingUp, TrendingDown, Activity, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import { Sidebar } from '../components/Sidebar';
import './Dashboard.css';

ChartJS.register(ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement, Title);

export const Dashboard = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchDashboardStats();
  }, []);

  const fetchDashboardStats = async () => {
    try {
      const response = await axios.get('/api/transactions/dashboard');
      setStats(response.data);
      setError('');
    } catch (err) {
      setError('Failed to load dashboard data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="layout">
        <Sidebar />
        <div className="main-content">
          <div className="loading">Loading dashboard...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="layout">
        <Sidebar />
        <div className="main-content">
          <div className="error-message">{error}</div>
        </div>
      </div>
    );
  }

  const fraudVsLegitData = {
    labels: ['Fraud Detected', 'Legitimate'],
    datasets: [
      {
        label: 'Transactions',
        data: [stats?.fraud_detected || 0, stats?.legitimate_transactions || 0],
        backgroundColor: ['#ef4444', '#10b981'],
        borderColor: ['#dc2626', '#059669'],
        borderWidth: 2,
      },
    ],
  };

  const approvalData = {
    labels: ['Approved', 'Rejected'],
    datasets: [
      {
        label: 'Transactions',
        data: [stats?.approved_transactions || 0, stats?.rejected_transactions || 0],
        backgroundColor: ['#3b82f6', '#f59e0b'],
        borderColor: ['#2563eb', '#d97706'],
        borderWidth: 2,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          padding: 15,
          font: {
            size: 12,
          },
        },
      },
    },
  };

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <div className="page-header">
          <h1 className="page-title">Dashboard</h1>
          <p className="page-subtitle">Overview of your fraud detection statistics</p>
        </div>

        <div className="stats-grid">
          <div className="stat-card stat-primary">
            <div className="stat-icon">
              <Activity size={24} />
            </div>
            <div className="stat-content">
              <div className="stat-label">Total Transactions</div>
              <div className="stat-value">{stats?.total_transactions || 0}</div>
            </div>
          </div>

          <div className="stat-card stat-success">
            <div className="stat-icon">
              <CheckCircle size={24} />
            </div>
            <div className="stat-content">
              <div className="stat-label">Approved</div>
              <div className="stat-value">{stats?.approved_transactions || 0}</div>
              <div className="stat-badge stat-badge-success">
                {stats?.approval_rate?.toFixed(1) || 0}%
              </div>
            </div>
          </div>

          <div className="stat-card stat-warning">
            <div className="stat-icon">
              <XCircle size={24} />
            </div>
            <div className="stat-content">
              <div className="stat-label">Rejected</div>
              <div className="stat-value">{stats?.rejected_transactions || 0}</div>
            </div>
          </div>

          <div className="stat-card stat-danger">
            <div className="stat-icon">
              <AlertTriangle size={24} />
            </div>
            <div className="stat-content">
              <div className="stat-label">Fraud Detected</div>
              <div className="stat-value">{stats?.fraud_detected || 0}</div>
              <div className="stat-badge stat-badge-danger">
                {stats?.fraud_percentage?.toFixed(1) || 0}%
              </div>
            </div>
          </div>
        </div>

        {stats?.total_transactions > 0 ? (
          <div className="charts-grid">
            <div className="chart-card">
              <h3 className="chart-title">Fraud vs Legitimate</h3>
              <div className="chart-container">
                <Doughnut data={fraudVsLegitData} options={chartOptions} />
              </div>
            </div>

            <div className="chart-card">
              <h3 className="chart-title">Approved vs Rejected</h3>
              <div className="chart-container">
                <Doughnut data={approvalData} options={chartOptions} />
              </div>
            </div>
          </div>
        ) : (
          <div className="empty-state">
            <AlertTriangle size={48} />
            <h3>No Data Available</h3>
            <p>Upload a CSV file to see your fraud detection analytics</p>
          </div>
        )}
      </div>
    </div>
  );
};

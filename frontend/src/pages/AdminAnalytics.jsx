import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Bar } from 'react-chartjs-2';
import { Users, Activity, AlertTriangle, TrendingUp } from 'lucide-react';
import { Sidebar } from '../components/Sidebar';
import './AdminAnalytics.css';

export const AdminAnalytics = () => {
  const [stats, setStats] = useState(null);
  const [fraudRates, setFraudRates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchAdminData();
  }, []);

  const fetchAdminData = async () => {
    try {
      const [statsResponse, ratesResponse] = await Promise.all([
        axios.get('/api/admin/analytics'),
        axios.get('/api/admin/fraud-rates-by-user'),
      ]);

      setStats(statsResponse.data);
      setFraudRates(ratesResponse.data);
      setError('');
    } catch (err) {
      setError('Failed to load admin analytics');
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
          <div className="loading">Loading admin analytics...</div>
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

  const fraudRateChartData = {
    labels: fraudRates.map(user => user.username),
    datasets: [
      {
        label: 'Fraud Rate (%)',
        data: fraudRates.map(user => user.fraud_rate),
        backgroundColor: 'rgba(239, 68, 68, 0.6)',
        borderColor: 'rgba(239, 68, 68, 1)',
        borderWidth: 2,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: true,
        position: 'top',
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        max: 100,
        ticks: {
          callback: function(value) {
            return value + '%';
          }
        }
      },
    },
  };

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <div className="page-header">
          <h1 className="page-title">Admin Analytics</h1>
          <p className="page-subtitle">Global fraud detection statistics across all users</p>
        </div>

        <div className="stats-grid">
          <div className="stat-card stat-primary">
            <div className="stat-icon">
              <Users size={24} />
            </div>
            <div className="stat-content">
              <div className="stat-label">Total Users</div>
              <div className="stat-value">{stats?.total_users || 0}</div>
            </div>
          </div>

          <div className="stat-card stat-info">
            <div className="stat-icon">
              <Activity size={24} />
            </div>
            <div className="stat-content">
              <div className="stat-label">Total Transactions</div>
              <div className="stat-value">{stats?.total_transactions || 0}</div>
            </div>
          </div>

          <div className="stat-card stat-danger">
            <div className="stat-icon">
              <AlertTriangle size={24} />
            </div>
            <div className="stat-content">
              <div className="stat-label">Total Fraud Detected</div>
              <div className="stat-value">{stats?.total_fraud_detected || 0}</div>
              <div className="stat-badge stat-badge-danger">
                {stats?.global_fraud_rate?.toFixed(1) || 0}%
              </div>
            </div>
          </div>

          <div className="stat-card stat-success">
            <div className="stat-icon">
              <TrendingUp size={24} />
            </div>
            <div className="stat-content">
              <div className="stat-label">Global Approval Rate</div>
              <div className="stat-value">
                {stats?.global_approval_rate?.toFixed(1) || 0}%
              </div>
            </div>
          </div>
        </div>

        <div className="admin-section">
          <div className="section-card">
            <h3 className="section-title">Transaction Distribution</h3>
            <div className="distribution-grid">
              <div className="distribution-item">
                <span className="distribution-label">Approved</span>
                <span className="distribution-value approved">
                  {stats?.approved_transactions || 0}
                </span>
              </div>
              <div className="distribution-item">
                <span className="distribution-label">Rejected</span>
                <span className="distribution-value rejected">
                  {stats?.rejected_transactions || 0}
                </span>
              </div>
            </div>
          </div>
        </div>

        {fraudRates.length > 0 ? (
          <>
            <div className="admin-section">
              <div className="section-card">
                <h3 className="section-title">Fraud Rate by User</h3>
                <div className="chart-container-large">
                  <Bar data={fraudRateChartData} options={chartOptions} />
                </div>
              </div>
            </div>

            <div className="admin-section">
              <div className="section-card">
                <h3 className="section-title">User Fraud Statistics</h3>
                <div className="table-container">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Username</th>
                        <th>Email</th>
                        <th>Total Transactions</th>
                        <th>Fraud Count</th>
                        <th>Fraud Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fraudRates.map((user, index) => (
                        <tr key={index}>
                          <td className="username-cell">{user.username}</td>
                          <td className="email-cell">{user.email}</td>
                          <td>{user.total_transactions}</td>
                          <td className="fraud-count">{user.fraud_count}</td>
                          <td>
                            <span className={`rate-badge ${user.fraud_rate > 50 ? 'high' : user.fraud_rate > 20 ? 'medium' : 'low'}`}>
                              {user.fraud_rate.toFixed(1)}%
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="empty-state">
            <AlertTriangle size={48} />
            <h3>No User Data Available</h3>
            <p>Users need to upload transaction data to see analytics</p>
          </div>
        )}
      </div>
    </div>
  );
};

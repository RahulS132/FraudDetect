import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Bar, Line, Scatter } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  PointElement,
  LineElement,
  Filler,
} from 'chart.js';
import { Users, Activity, AlertTriangle, TrendingUp } from 'lucide-react';
import { Sidebar } from '../components/Sidebar';
import './AdminAnalytics.css';

ChartJS.register(
  ArcElement,
  Tooltip,
  Legend,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  PointElement,
  LineElement,
  Filler
);

export const AdminAnalytics = () => {
  const [stats, setStats] = useState(null);
  const [fraudRates, setFraudRates] = useState([]);
  const [anomalyDist, setAnomalyDist] = useState(null);
  const [fraudTrend, setFraudTrend] = useState(null);
  const [vFeatures, setVFeatures] = useState(null);
  const [confusionMatrix, setConfusionMatrix] = useState(null);
  const [amountDist, setAmountDist] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchAdminData();
  }, []);

  const fetchAdminData = async () => {
    try {
      const [
        statsRes,
        ratesRes,
        anomalyRes,
        trendRes,
        vFeatRes,
        confRes,
        amountRes,
      ] = await Promise.all([
        axios.get('/api/admin/analytics'),
        axios.get('/api/admin/fraud-rates-by-user'),
        axios.get('/api/admin/global-anomaly-distribution'),
        axios.get('/api/admin/fraud-rate-trend'),
        axios.get('/api/admin/v-feature-boxplots'),
        axios.get('/api/admin/confusion-matrix'),
        axios.get('/api/admin/amount-distribution'),
      ]);

      setStats(statsRes.data);
      setFraudRates(ratesRes.data);
      setAnomalyDist(anomalyRes.data);
      setFraudTrend(trendRes.data);
      setVFeatures(vFeatRes.data);
      setConfusionMatrix(confRes.data);
      setAmountDist(amountRes.data);
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

  // ── Fraud Rate by User (existing bar chart) ───────────────────────────────

  const fraudRateChartData = {
    labels: fraudRates.map(u => u.username),
    datasets: [
      {
        label: 'Fraud Rate (%)',
        data: fraudRates.map(u => u.fraud_rate),
        backgroundColor: 'rgba(239, 68, 68, 0.6)',
        borderColor: 'rgba(239, 68, 68, 1)',
        borderWidth: 2,
      },
    ],
  };

  const fraudRateOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: true, position: 'top' } },
    scales: {
      y: {
        beginAtZero: true,
        max: 100,
        ticks: { callback: v => v + '%' },
      },
    },
  };

  // ── Global Anomaly Score Distribution ─────────────────────────────────────

  const hasAnomalyDist = anomalyDist?.bins?.length > 0;

  const anomalyHistData = {
    labels: anomalyDist?.bins || [],
    datasets: [
      {
        label: 'Fraud',
        data: anomalyDist?.fraud_counts || [],
        backgroundColor: 'rgba(239, 68, 68, 0.75)',
        borderColor: '#ef4444',
        borderWidth: 1,
        stack: 'stack',
      },
      {
        label: 'Legitimate',
        data: anomalyDist?.legit_counts || [],
        backgroundColor: 'rgba(16, 185, 129, 0.65)',
        borderColor: '#10b981',
        borderWidth: 1,
        stack: 'stack',
      },
    ],
  };

  const anomalyHistOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'top' } },
    scales: {
      x: {
        stacked: true,
        title: { display: true, text: 'Anomaly Score (lower = more anomalous)' },
        ticks: { maxRotation: 45, autoSkip: true, maxTicksLimit: 10 },
      },
      y: {
        stacked: true,
        title: { display: true, text: 'Transaction Count' },
        beginAtZero: true,
      },
    },
  };

  // ── Fraud Rate Trend ──────────────────────────────────────────────────────

  const hasTrend = fraudTrend?.dates?.length > 0;

  const trendData = {
    labels: fraudTrend?.dates || [],
    datasets: [
      {
        label: 'Fraud Rate (%)',
        data: fraudTrend?.fraud_rates || [],
        borderColor: '#ef4444',
        backgroundColor: 'rgba(239, 68, 68, 0.12)',
        fill: true,
        tension: 0.3,
        pointRadius: 4,
        yAxisID: 'yRate',
      },
      {
        label: 'Total Transactions',
        data: fraudTrend?.total_counts || [],
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.08)',
        fill: true,
        tension: 0.3,
        pointRadius: 4,
        yAxisID: 'yCount',
      },
    ],
  };

  const trendOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { position: 'top' } },
    scales: {
      x: { title: { display: true, text: 'Date' } },
      yRate: {
        type: 'linear',
        position: 'left',
        title: { display: true, text: 'Fraud Rate (%)' },
        beginAtZero: true,
      },
      yCount: {
        type: 'linear',
        position: 'right',
        title: { display: true, text: 'Transaction Count' },
        beginAtZero: true,
        grid: { drawOnChartArea: false },
      },
    },
  };

  // ── V-Feature Box Plots (IQR floating bars, horizontal) ───────────────────

  const hasVFeatures = vFeatures?.features?.length > 0;

  const vFeatureData = {
    labels: vFeatures?.features || [],
    datasets: [
      {
        label: 'Fraud (IQR Q1–Q3)',
        data: vFeatures?.fraud?.map(s => [s.q1, s.q3]) || [],
        backgroundColor: 'rgba(239, 68, 68, 0.6)',
        borderColor: '#ef4444',
        borderWidth: 1,
        borderSkipped: false,
      },
      {
        label: 'Legitimate (IQR Q1–Q3)',
        data: vFeatures?.legit?.map(s => [s.q1, s.q3]) || [],
        backgroundColor: 'rgba(16, 185, 129, 0.55)',
        borderColor: '#10b981',
        borderWidth: 1,
        borderSkipped: false,
      },
    ],
  };

  const vFeatureOptions = {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'top' },
      tooltip: {
        callbacks: {
          label: (ctx) => {
            const idx = ctx.dataIndex;
            const isF = ctx.datasetIndex === 0;
            const src = isF ? vFeatures?.fraud : vFeatures?.legit;
            const s = src?.[idx];
            if (!s) return ctx.dataset.label;
            return [
              `${ctx.dataset.label}`,
              `  min: ${s.min.toFixed(3)}`,
              `  Q1: ${s.q1.toFixed(3)}`,
              `  median: ${s.median.toFixed(3)}`,
              `  Q3: ${s.q3.toFixed(3)}`,
              `  max: ${s.max.toFixed(3)}`,
            ];
          },
        },
      },
    },
    scales: {
      x: { title: { display: true, text: 'Feature Value (PCA-scaled)' } },
      y: { ticks: { font: { size: 11 } } },
    },
  };

  // ── Amount Distribution ───────────────────────────────────────────────────

  const hasAmountDist = amountDist?.bins?.length > 0;

  const amountDistData = {
    labels: amountDist?.bins || [],
    datasets: [
      {
        label: 'Fraud',
        data: amountDist?.fraud_counts || [],
        backgroundColor: 'rgba(239, 68, 68, 0.6)',
        borderColor: '#ef4444',
        borderWidth: 1,
      },
      {
        label: 'Legitimate',
        data: amountDist?.legit_counts || [],
        backgroundColor: 'rgba(16, 185, 129, 0.5)',
        borderColor: '#10b981',
        borderWidth: 1,
      },
    ],
  };

  const amountDistOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'top' } },
    scales: {
      x: {
        title: { display: true, text: 'Transaction Amount' },
        ticks: { maxRotation: 45, autoSkip: true, maxTicksLimit: 10 },
      },
      y: {
        title: { display: true, text: 'Count' },
        beginAtZero: true,
      },
    },
  };

  // ── Confusion Matrix helper ───────────────────────────────────────────────

  const cm = confusionMatrix;
  const hasCM = cm && (cm.true_positive + cm.false_positive + cm.true_negative + cm.false_negative) > 0;

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <div className="page-header">
          <h1 className="page-title">Admin Analytics</h1>
          <p className="page-subtitle">Global fraud detection statistics across all users</p>
        </div>

        {/* ── Stat Cards ─────────────────────────────────────────────────── */}
        <div className="stats-grid">
          <div className="stat-card stat-primary">
            <div className="stat-icon"><Users size={24} /></div>
            <div className="stat-content">
              <div className="stat-label">Total Users</div>
              <div className="stat-value">{stats?.total_users || 0}</div>
            </div>
          </div>

          <div className="stat-card stat-info">
            <div className="stat-icon"><Activity size={24} /></div>
            <div className="stat-content">
              <div className="stat-label">Total Transactions</div>
              <div className="stat-value">{stats?.total_transactions || 0}</div>
            </div>
          </div>

          <div className="stat-card stat-danger">
            <div className="stat-icon"><AlertTriangle size={24} /></div>
            <div className="stat-content">
              <div className="stat-label">Total Fraud Detected</div>
              <div className="stat-value">{stats?.total_fraud_detected || 0}</div>
              <div className="stat-badge stat-badge-danger">
                {stats?.global_fraud_rate?.toFixed(1) || 0}%
              </div>
            </div>
          </div>

          <div className="stat-card stat-success">
            <div className="stat-icon"><TrendingUp size={24} /></div>
            <div className="stat-content">
              <div className="stat-label">Global Approval Rate</div>
              <div className="stat-value">
                {stats?.global_approval_rate?.toFixed(1) || 0}%
              </div>
            </div>
          </div>
        </div>
        {/* ── Transaction Distribution ────────────────────────────────────── */}
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

        {/* ── Confusion Matrix ────────────────────────────────────────────── */}
        {hasCM && (
          <div className="admin-section">
            <div className="section-card">
              <h3 className="section-title">Confusion Matrix</h3>
              <p className="section-subtitle">
                actual_class vs is_fraud across all detection results
              </p>

              <div className="cm-grid">
                <div className="cm-axis-label cm-col-header" />
                <div className="cm-col-header">Predicted: Fraud</div>
                <div className="cm-col-header">Predicted: Legit</div>

                <div className="cm-row-header">Actual: Fraud</div>
                <div className="cm-cell cm-tp">
                  <div className="cm-cell-label">True Positive</div>
                  <div className="cm-cell-value">{cm.true_positive.toLocaleString()}</div>
                </div>
                <div className="cm-cell cm-fn">
                  <div className="cm-cell-label">False Negative</div>
                  <div className="cm-cell-value">{cm.false_negative.toLocaleString()}</div>
                </div>

                <div className="cm-row-header">Actual: Legit</div>
                <div className="cm-cell cm-fp">
                  <div className="cm-cell-label">False Positive</div>
                  <div className="cm-cell-value">{cm.false_positive.toLocaleString()}</div>
                </div>
                <div className="cm-cell cm-tn">
                  <div className="cm-cell-label">True Negative</div>
                  <div className="cm-cell-value">{cm.true_negative.toLocaleString()}</div>
                </div>
              </div>

              <div className="cm-metrics">
                <div className="cm-metric">
                  <span className="cm-metric-label">Accuracy</span>
                  <span className="cm-metric-value">{cm.accuracy}%</span>
                </div>
                <div className="cm-metric">
                  <span className="cm-metric-label">Precision</span>
                  <span className="cm-metric-value">{cm.precision}%</span>
                </div>
                <div className="cm-metric">
                  <span className="cm-metric-label">Recall</span>
                  <span className="cm-metric-value">{cm.recall}%</span>
                </div>
                <div className="cm-metric">
                  <span className="cm-metric-label">F1 Score</span>
                  <span className="cm-metric-value">{cm.f1_score}%</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ── V-Feature IQR ───────────────────────────────────────────────── */}
        {hasVFeatures && (
          <div className="admin-section">
            <div className="section-card">
              <h3 className="section-title">V-Feature IQR: Fraud vs Legitimate</h3>
              <p className="section-subtitle">
                Interquartile range (Q1–Q3) for each PCA component, split by class. Hover for full stats. Sampled up to 3,000 records per class.
              </p>
              <div className="chart-container-vfeature">
                <Bar data={vFeatureData} options={vFeatureOptions} />
              </div>
            </div>
          </div>
        )}

        {fraudRates.length > 0 ? (
          <>
            {/* ── Global Anomaly Score Distribution ──────────────────────── */}
            {hasAnomalyDist && (
              <div className="admin-section">
                <div className="section-card">
                  <h3 className="section-title">Global Anomaly Score Distribution</h3>
                  <p className="section-subtitle">
                    Score distribution across all users — use this to tune the contamination threshold (currently 0.1)
                  </p>
                  <div className="chart-container-large">
                    <Bar data={anomalyHistData} options={anomalyHistOptions} />
                  </div>
                </div>
              </div>
            )}

            {/* ── Fraud Rate Trend ────────────────────────────────────────── */}
            {hasTrend && (
              <div className="admin-section">
                <div className="section-card">
                  <h3 className="section-title">Fraud Rate Trend Over Time</h3>
                  <p className="section-subtitle">
                    Spot if a particular CSV batch skewed the fraud rate
                  </p>
                  <div className="chart-container-large">
                    <Line data={trendData} options={trendOptions} />
                  </div>
                </div>
              </div>
            )}

            {/* ── Amount Distribution by Class ────────────────────────────── */}
            {hasAmountDist && (
              <div className="admin-section">
                <div className="section-card">
                  <h3 className="section-title">Amount Distribution by Class</h3>
                  <p className="section-subtitle">
                    Fraud vs legitimate transaction amounts (capped at 99th percentile). Sampled up to 3,000 per class.
                  </p>
                  <div className="chart-container-large">
                    <Bar data={amountDistData} options={amountDistOptions} />
                  </div>
                </div>
              </div>
            )}

            {/* ── Fraud Rate by User ──────────────────────────────────────── */}
            <div className="admin-section">
              <div className="section-card">
                <h3 className="section-title">Fraud Rate by User</h3>
                <div className="chart-container-large">
                  <Bar data={fraudRateChartData} options={fraudRateOptions} />
                </div>
              </div>
            </div>

            {/* ── User Fraud Statistics Table ─────────────────────────────── */}
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

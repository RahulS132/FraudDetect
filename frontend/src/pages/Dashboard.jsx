import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/api';
import { useRealtime } from '../contexts/RealtimeContext';
import { TopBar } from '../components/TopBar';
import { Doughnut, Bar, Scatter, Line } from 'react-chartjs-2';
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
import { TrendingUp, TrendingDown, Activity, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import { Sidebar } from '../components/Sidebar';
import './Dashboard.css';

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

export const Dashboard = () => {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [anomalyDist, setAnomalyDist] = useState(null);
  const [amountVsAnomaly, setAmountVsAnomaly] = useState(null);
  const [txOverTime, setTxOverTime] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const { onTransactionsUpdated } = useRealtime();

  const fetchAll = useCallback(async () => {
    try {
      const [statsRes, distRes, scatterRes, timeRes] = await Promise.all([
        api.get('/api/transactions/dashboard'),
        api.get('/api/transactions/anomaly-score-distribution'),
        api.get('/api/transactions/amount-vs-anomaly'),
        api.get('/api/transactions/transactions-over-time'),
      ]);
      setStats(statsRes.data);
      setAnomalyDist(distRes.data);
      setAmountVsAnomaly(scatterRes.data);
      setTxOverTime(timeRes.data);
      setError('');
    } catch (err) {
      setError('Failed to load dashboard data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // Real-time: re-fetch all dashboard data whenever transactions change
  // (CSV upload, admin bulk-create, tag edits) — no page refresh needed.
  useEffect(() => {
    const unsub = onTransactionsUpdated(() => fetchAll());
    return unsub;
  }, [onTransactionsUpdated, fetchAll]);

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

  // ── Existing doughnut data ────────────────────────────────────────────────

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

  const doughnutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: { padding: 15, font: { size: 12 } },
      },
    },
  };

  // ── Anomaly Score Distribution (stacked bar histogram) ────────────────────

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
    plugins: {
      legend: { position: 'top' },
      title: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => `Score bin: ${items[0].label}`,
        },
      },
    },
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

  // ── Amount vs Anomaly Score (scatter) ─────────────────────────────────────

  const hasScatter =
    amountVsAnomaly &&
    (amountVsAnomaly.fraud_points?.length > 0 || amountVsAnomaly.legit_points?.length > 0);

  const scatterData = {
    datasets: [
      {
        label: 'Fraud',
        data: amountVsAnomaly?.fraud_points || [],
        backgroundColor: 'rgba(239, 68, 68, 0.55)',
        pointRadius: 4,
        pointHoverRadius: 6,
      },
      {
        label: 'Legitimate',
        data: amountVsAnomaly?.legit_points || [],
        backgroundColor: 'rgba(16, 185, 129, 0.35)',
        pointRadius: 3,
        pointHoverRadius: 5,
      },
    ],
  };

  const scatterOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'top' },
      tooltip: {
        callbacks: {
          label: (ctx) =>
            `${ctx.dataset.label}: $${ctx.parsed.x.toFixed(2)}, score ${ctx.parsed.y.toFixed(4)}`,
        },
      },
    },
    scales: {
      x: { title: { display: true, text: 'Transaction Amount ($)' } },
      y: { title: { display: true, text: 'Anomaly Score' } },
    },
  };

  // ── Transactions Over Time (line) ─────────────────────────────────────────

  const hasTime = txOverTime?.dates?.length > 0;

  const timeData = {
    labels: txOverTime?.dates || [],
    datasets: [
      {
        label: 'Total Transactions',
        data: txOverTime?.total_counts || [],
        borderColor: '#3b82f6',
        backgroundColor: 'rgba(59, 130, 246, 0.12)',
        fill: true,
        tension: 0.3,
        pointRadius: 4,
      },
      {
        label: 'Fraud',
        data: txOverTime?.fraud_counts || [],
        borderColor: '#ef4444',
        backgroundColor: 'rgba(239, 68, 68, 0.12)',
        fill: true,
        tension: 0.3,
        pointRadius: 4,
      },
    ],
  };

  const timeOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { position: 'top' } },
    scales: {
      x: { title: { display: true, text: 'Upload Date' } },
      y: {
        title: { display: true, text: 'Count' },
        beginAtZero: true,
      },
    },
  };

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <TopBar
          title="Dashboard"
          subtitle="Overview of your fraud detection statistics"
        />

        {/* ── Stat Cards (clickable → filtered Transactions) ─────────────── */}
        <div className="stats-grid">
          <div
            className="stat-card stat-primary stat-clickable"
            role="button" tabIndex={0}
            onClick={() => navigate('/transactions')}
            onKeyDown={(e) => e.key === 'Enter' && navigate('/transactions')}
          >
            <div className="stat-icon"><Activity size={24} /></div>
            <div className="stat-content">
              <div className="stat-label">Total Transactions</div>
              <div className="stat-value">{stats?.total_transactions || 0}</div>
            </div>
          </div>

          <div
            className="stat-card stat-success stat-clickable"
            role="button" tabIndex={0}
            onClick={() => navigate('/transactions?filter=approved')}
            onKeyDown={(e) => e.key === 'Enter' && navigate('/transactions?filter=approved')}
          >
            <div className="stat-icon"><CheckCircle size={24} /></div>
            <div className="stat-content">
              <div className="stat-label">Approved</div>
              <div className="stat-value">{stats?.approved_transactions || 0}</div>
              <div className="stat-badge stat-badge-success">
                {stats?.approval_rate?.toFixed(1) || 0}%
              </div>
            </div>
          </div>

          <div
            className="stat-card stat-warning stat-clickable"
            role="button" tabIndex={0}
            onClick={() => navigate('/transactions?filter=fraud')}
            onKeyDown={(e) => e.key === 'Enter' && navigate('/transactions?filter=fraud')}
          >
            <div className="stat-icon"><XCircle size={24} /></div>
            <div className="stat-content">
              <div className="stat-label">Rejected</div>
              <div className="stat-value">{stats?.rejected_transactions || 0}</div>
            </div>
          </div>

          <div
            className="stat-card stat-danger stat-clickable"
            role="button" tabIndex={0}
            onClick={() => navigate('/transactions?filter=fraud')}
            onKeyDown={(e) => e.key === 'Enter' && navigate('/transactions?filter=fraud')}
          >
            <div className="stat-icon"><AlertTriangle size={24} /></div>
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
          <>
            {/* ── Doughnut Charts ─────────────────────────────────────────── */}
            <div className="charts-grid">
              <div className="chart-card">
                <h3 className="chart-title">Fraud vs Legitimate</h3>
                <div className="chart-container">
                  <Doughnut data={fraudVsLegitData} options={doughnutOptions} />
                </div>
              </div>

              <div className="chart-card">
                <h3 className="chart-title">Approved vs Rejected</h3>
                <div className="chart-container">
                  <Doughnut data={approvalData} options={doughnutOptions} />
                </div>
              </div>
            </div>

            {/* ── Anomaly Score Distribution ──────────────────────────────── */}
            {hasAnomalyDist && (
              <div className="chart-section">
                <div className="chart-card chart-card-full">
                  <h3 className="chart-title">Anomaly Score Distribution</h3>
                  <p className="chart-subtitle">
                    Where your transactions cluster relative to the fraud threshold — lower scores are more anomalous
                  </p>
                  <div className="chart-container chart-container-tall">
                    <Bar data={anomalyHistData} options={anomalyHistOptions} />
                  </div>
                </div>
              </div>
            )}

            {/* ── Scatter + Line ──────────────────────────────────────────── */}
            <div className="charts-grid">
              {hasScatter && (
                <div className="chart-card">
                  <h3 className="chart-title">Amount vs Anomaly Score</h3>
                  <p className="chart-subtitle">
                    Do high-value transactions get flagged? Sample of up to 2,000 transactions
                  </p>
                  <div className="chart-container chart-container-tall">
                    <Scatter data={scatterData} options={scatterOptions} />
                  </div>
                </div>
              )}

              {hasTime && (
                <div className="chart-card">
                  <h3 className="chart-title">Transactions Over Time</h3>
                  <p className="chart-subtitle">
                    Upload volume and fraud events on the same timeline
                  </p>
                  <div className="chart-container chart-container-tall">
                    <Line data={timeData} options={timeOptions} />
                  </div>
                </div>
              )}
            </div>
          </>
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

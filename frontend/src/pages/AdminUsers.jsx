import React, { useState, useEffect, useCallback } from 'react';
import { Bar, Doughnut } from 'react-chartjs-2';
import {
  Chart as ChartJS, ArcElement, Tooltip, Legend, CategoryScale,
  LinearScale, BarElement,
} from 'chart.js';
import {
  Users, Search, ShieldAlert, Activity, DollarSign, TrendingUp, Loader, Inbox,
} from 'lucide-react';
import api from '../lib/api';
import { Sidebar } from '../components/Sidebar';
import { TopBar } from '../components/TopBar';
import { TransactionsExplorer } from '../components/TransactionsExplorer';
import { AdminAccountPanel } from '../components/AdminAccountPanel';
import { StatusBadge } from '../components/StatusBadge';
import { useRealtime } from '../contexts/RealtimeContext';
import { useToast } from '../contexts/ToastContext';
import './AdminUsers.css';

ChartJS.register(ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement);

const fmtMoney = (v) =>
  v == null ? '$0.00' : `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const RISK_COLORS = { low: '#10b981', medium: '#f59e0b', high: '#ef4444', critical: '#b91c1c' };

export const AdminUsers = () => {
  const toast = useToast();
  const { onTransactionsUpdated } = useRealtime();

  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);

  const loadUsers = useCallback(async () => {
    setUsersLoading(true);
    try {
      const res = await api.get('/api/admin/users', { params: search ? { search } : {} });
      setUsers(res.data || []);
    } catch (err) {
      toast.error(err.cleanMessage || 'Failed to load users');
    } finally {
      setUsersLoading(false);
    }
  }, [search, toast]);

  useEffect(() => {
    const t = setTimeout(loadUsers, 300);
    return () => clearTimeout(t);
  }, [loadUsers]);

  const loadAnalytics = useCallback(async (userId) => {
    if (!userId) return;
    setAnalyticsLoading(true);
    try {
      const res = await api.get(`/api/admin/users/${userId}/analytics`);
      setAnalytics(res.data);
    } catch (err) {
      toast.error(err.cleanMessage || 'Failed to load analytics');
    } finally {
      setAnalyticsLoading(false);
    }
  }, [toast]);

  const selectUser = (u) => {
    setSelected(u);
    setAnalytics(null);
    loadAnalytics(u.user_id);
  };

  // Live refresh when data changes for the selected user.
  useEffect(() => {
    const unsub = onTransactionsUpdated(() => {
      loadUsers();
      if (selected) loadAnalytics(selected.user_id);
    });
    return unsub;
  }, [onTransactionsUpdated, loadUsers, loadAnalytics, selected]);

  const spendingData = analytics && {
    labels: analytics.spending_by_tag.map((s) => s.tag),
    datasets: [{
      data: analytics.spending_by_tag.map((s) => s.amount),
      backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#64748b'],
      borderWidth: 1,
    }],
  };

  const timeData = analytics && {
    labels: analytics.transactions_over_time.dates || [],
    datasets: [
      {
        label: 'Transactions',
        data: analytics.transactions_over_time.total_counts || [],
        backgroundColor: 'rgba(59,130,246,0.6)',
      },
      {
        label: 'Fraud',
        data: analytics.transactions_over_time.fraud_counts || [],
        backgroundColor: 'rgba(239,68,68,0.7)',
      },
    ],
  };

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <TopBar
          title="User Management"
          subtitle="Select a user to inspect their transactions, fraud history, and risk"
        />

        <div className="au-grid">
          {/* ── User list ── */}
          <div className="au-userlist">
            <div className="au-search">
              <Search size={16} />
              <input
                placeholder="Search users…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            {usersLoading ? (
              <div className="au-state"><Loader size={20} className="au-spin" /> Loading…</div>
            ) : users.length === 0 ? (
              <div className="au-state"><Inbox size={22} /> No users found</div>
            ) : (
              <ul className="au-users">
                {users.map((u) => (
                  <li
                    key={u.user_id}
                    className={selected?.user_id === u.user_id ? 'active' : ''}
                    onClick={() => selectUser(u)}
                  >
                    <div className="au-user-main">
                      <span className="au-user-name">{u.username}</span>
                      <span className="au-user-email">{u.email}</span>
                    </div>
                    <div className="au-user-stats">
                      <StatusBadge status={u.status} size="sm" />
                      <span>{u.total_transactions} tx</span>
                      {u.fraud_count > 0 && (
                        <span className="au-user-fraud">{u.fraud_count} fraud</span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* ── Detail panel ── */}
          <div className="au-detail">
            {!selected ? (
              <div className="au-placeholder">
                <Users size={48} />
                <h3>Select a user</h3>
                <p>Choose a user from the list to view their full activity and analytics.</p>
              </div>
            ) : (
              <>
                <div className="au-detail-head">
                  <div>
                    <h2>{selected.username}</h2>
                    <p>{selected.email}</p>
                  </div>
                  {analytics && (
                    <div
                      className="au-risk"
                      style={{ '--risk': RISK_COLORS[analytics.risk_level] }}
                    >
                      <ShieldAlert size={18} />
                      <div>
                        <div className="au-risk-score">{analytics.risk_score}</div>
                        <div className="au-risk-level">{analytics.risk_level} risk</div>
                      </div>
                    </div>
                  )}
                </div>

                <AdminAccountPanel
                  key={selected.user_id}
                  userId={selected.user_id}
                  onChange={loadUsers}
                />

                {analyticsLoading ? (
                  <div className="au-state"><Loader size={22} className="au-spin" /> Loading analytics…</div>
                ) : analytics ? (
                  <>
                    <div className="au-cards">
                      <div className="au-card">
                        <Activity size={18} />
                        <div>
                          <span className="au-card-label">Transactions</span>
                          <span className="au-card-value">{analytics.total_transactions}</span>
                        </div>
                      </div>
                      <div className="au-card">
                        <ShieldAlert size={18} />
                        <div>
                          <span className="au-card-label">Fraud</span>
                          <span className="au-card-value">{analytics.fraud_detected} ({analytics.fraud_percentage}%)</span>
                        </div>
                      </div>
                      <div className="au-card">
                        <DollarSign size={18} />
                        <div>
                          <span className="au-card-label">Total Volume</span>
                          <span className="au-card-value">{fmtMoney(analytics.total_volume)}</span>
                        </div>
                      </div>
                      <div className="au-card">
                        <TrendingUp size={18} />
                        <div>
                          <span className="au-card-label">Avg Transaction</span>
                          <span className="au-card-value">{fmtMoney(analytics.avg_transaction)}</span>
                        </div>
                      </div>
                    </div>

                    <div className="au-charts">
                      {analytics.spending_by_tag.length > 0 && (
                        <div className="au-chart-card">
                          <h4>Spending by Tag</h4>
                          <div className="au-chart-wrap">
                            <Doughnut
                              data={spendingData}
                              options={{ responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { font: { size: 11 } } } } }}
                            />
                          </div>
                        </div>
                      )}
                      {(analytics.transactions_over_time.dates || []).length > 0 && (
                        <div className="au-chart-card">
                          <h4>Activity Over Time</h4>
                          <div className="au-chart-wrap">
                            <Bar
                              data={timeData}
                              options={{ responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'top' } }, scales: { x: { stacked: false }, y: { beginAtZero: true } } }}
                            />
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="au-tx-section">
                      <h4>Transaction History</h4>
                      <TransactionsExplorer
                        endpoint={`/api/admin/users/${selected.user_id}/transactions`}
                        compact
                      />
                    </div>
                  </>
                ) : null}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

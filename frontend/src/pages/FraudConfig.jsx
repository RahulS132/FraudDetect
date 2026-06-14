import React, { useState, useEffect, useCallback } from 'react';
import { Save, AlertOctagon, Loader, ShieldAlert } from 'lucide-react';
import api from '../lib/api';
import { Sidebar } from '../components/Sidebar';
import { TopBar } from '../components/TopBar';
import { TransactionDetailDrawer } from '../components/TransactionDetailDrawer';
import { useToast } from '../contexts/ToastContext';
import { useRealtime } from '../contexts/RealtimeContext';
import './AdminPages.css';

const fmtTime = (t) => (t ? new Date(t).toLocaleString() : '');

export const FraudConfig = () => {
  const toast = useToast();
  const { onTransactionsUpdated } = useRealtime();
  const [cfg, setCfg] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [reviewTxn, setReviewTxn] = useState(null);   // open detail drawer for review

  const loadCfg = useCallback(async () => {
    try {
      const res = await api.get('/api/admin/fraud-config');
      setCfg(res.data);
    } catch (err) { toast.error(err.cleanMessage || 'Failed to load config'); }
  }, [toast]);

  const loadEvents = useCallback(async () => {
    try {
      const res = await api.get('/api/admin/fraud-events', { params: { limit: 50 } });
      setEvents(res.data || []);
    } catch { /* non-fatal */ }
  }, []);

  useEffect(() => {
    (async () => { await Promise.all([loadCfg(), loadEvents()]); setLoading(false); })();
  }, [loadCfg, loadEvents]);

  useEffect(() => onTransactionsUpdated(() => loadEvents()), [onTransactionsUpdated, loadEvents]);

  const update = (k, v) => { setCfg((c) => ({ ...c, [k]: v })); setDirty(true); };

  const save = async () => {
    setSaving(true);
    try {
      const res = await api.patch('/api/admin/fraud-config', {
        auto_block_threshold: cfg.auto_block_threshold,
        auto_flag_threshold: cfg.auto_flag_threshold,
        flag_account_on_block: cfg.flag_account_on_block,
        notify_admins: cfg.notify_admins,
      });
      setCfg(res.data);
      setDirty(false);
      toast.success('Fraud configuration saved');
    } catch (err) {
      toast.error(err.cleanMessage || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  if (loading || !cfg) {
    return (
      <div className="layout"><Sidebar /><div className="main-content">
        <div className="adm-state"><Loader size={20} className="au-spin" /> Loading…</div>
      </div></div>
    );
  }

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <TopBar title="Fraud Auto-Blocking" subtitle="Tune the thresholds that automatically block or flag transactions" />
        <div className="adm-wrap">
          <div className="fc-grid">
            {/* Thresholds */}
            <div className="fc-card">
              <h3>Thresholds</h3>
              <p className="sub">Fraud scores range 0–100. Auto-block should sit above auto-flag.</p>

              <div className="fc-field">
                <label>Auto-block threshold <span className="fc-val">{cfg.auto_block_threshold}</span></label>
                <input type="range" min="0" max="100" step="1" value={cfg.auto_block_threshold}
                  onChange={(e) => update('auto_block_threshold', parseFloat(e.target.value))} />
              </div>
              <div className="fc-field">
                <label>Auto-flag threshold <span className="fc-val">{cfg.auto_flag_threshold}</span></label>
                <input type="range" min="0" max="100" step="1" value={cfg.auto_flag_threshold}
                  onChange={(e) => update('auto_flag_threshold', parseFloat(e.target.value))} />
              </div>

              <div className="fc-toggle">
                <span>Flag account on auto-block</span>
                <label className="switch">
                  <input type="checkbox" checked={!!cfg.flag_account_on_block} onChange={(e) => update('flag_account_on_block', e.target.checked)} />
                  <span className="track" />
                </label>
              </div>
              <div className="fc-toggle">
                <span>Notify admins on fraud</span>
                <label className="switch">
                  <input type="checkbox" checked={!!cfg.notify_admins} onChange={(e) => update('notify_admins', e.target.checked)} />
                  <span className="track" />
                </label>
              </div>

              <button className="adm-btn" style={{ marginTop: 18 }} onClick={save} disabled={saving || !dirty}>
                <Save size={16} /> {saving ? 'Saving…' : 'Save configuration'}
              </button>
              {cfg.updated_at && <p style={{ marginTop: 10, color: '#94a3b8', fontSize: '0.78rem' }}>Last updated {fmtTime(cfg.updated_at)} by {cfg.updated_by || 'system'}</p>}
            </div>

            {/* How it works */}
            <div className="fc-card">
              <h3><ShieldAlert size={16} style={{ verticalAlign: -3 }} /> How auto-blocking works</h3>
              <p className="sub">Every transaction is scored when created.</p>
              <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 12, fontSize: '0.86rem', color: '#475569' }}>
                <li><span className="pill block">≥ {cfg.auto_block_threshold}</span> &nbsp;Transaction is blocked, a fraud event is logged{cfg.flag_account_on_block ? ', and the account moves to Under Review' : ''}.</li>
                <li><span className="pill flag">≥ {cfg.auto_flag_threshold}</span> &nbsp;Transaction is flagged for review but still posts.</li>
                <li><span className="pill none">below</span> &nbsp;Transaction proceeds normally.</li>
              </ul>
            </div>
          </div>

          {/* Recent fraud events */}
          <div className="adm-card" style={{ marginTop: 18 }}>
            <div style={{ padding: '14px 16px', borderBottom: '1px solid #f1f5f9', fontWeight: 700, color: '#0f172a', display: 'flex', alignItems: 'center', gap: 8 }}>
              <AlertOctagon size={16} /> Recent Fraud Events
            </div>
            {events.length === 0 ? (
              <div className="adm-state">No fraud events yet</div>
            ) : (
              <table className="adm-table">
                <thead><tr><th>When</th><th>User</th><th>Score</th><th>Severity</th><th>Action</th><th>Reason</th><th></th></tr></thead>
                <tbody>
                  {events.map((e) => (
                    <tr
                      key={e.id}
                      onClick={() => e.transaction_id && setReviewTxn(e.transaction_id)}
                      style={{ cursor: e.transaction_id ? 'pointer' : 'default' }}
                      title="Click to view details and approve/deny"
                    >
                      <td style={{ whiteSpace: 'nowrap' }}>{fmtTime(e.created_at)}</td>
                      <td>{e.username || e.user_id || '—'}</td>
                      <td><strong>{e.fraud_score}</strong></td>
                      <td><span className={`pill ${e.severity}`}>{e.severity}</span></td>
                      <td><span className={`pill ${e.action === 'blocked' ? 'block' : 'flag'}`}>{e.action}</span></td>
                      <td style={{ color: '#64748b', fontSize: '0.8rem' }}>{e.reason}</td>
                      <td style={{ color: '#2563eb', fontSize: '0.8rem', fontWeight: 600, whiteSpace: 'nowrap' }}>Review →</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {reviewTxn && (
        <TransactionDetailDrawer
          transactionId={reviewTxn}
          reviewable
          canEdit={false}
          onClose={() => setReviewTxn(null)}
          onReviewed={() => { loadEvents(); }}
        />
      )}
    </div>
  );
};

export default FraudConfig;

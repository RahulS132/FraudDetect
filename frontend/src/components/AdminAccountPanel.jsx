import React, { useState, useEffect, useCallback } from 'react';
import {
  Wallet, PlusCircle, MinusCircle, Edit3, CreditCard, Snowflake,
  RotateCcw, Ban, ShieldCheck, Loader, History, KeyRound, MailCheck, MailX, Monitor,
} from 'lucide-react';
import api from '../lib/api';
import { useToast } from '../contexts/ToastContext';
import { StatusBadge } from './StatusBadge';
import './Account.css';

const fmtMoney = (v) =>
  v == null ? '$0.00' : `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const BLOCK_REASONS = [
  { value: 'fraud', label: 'Fraud' },
  { value: 'suspicious_activity', label: 'Suspicious Activity' },
  { value: 'manual_review', label: 'Manual Review' },
  { value: 'account_violation', label: 'Account Violation' },
  { value: 'custom', label: 'Custom Reason' },
];

/**
 * Admin panel for one user's balance, credit, freeze/reset and block status.
 * Self-fetches the account; calls `onChange` after any mutation so the parent
 * list/summary can refresh.
 */
export const AdminAccountPanel = ({ userId, onChange }) => {
  const toast = useToast();
  const [acct, setAcct] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null); // {type, ...}
  const [busy, setBusy] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [logins, setLogins] = useState(null);
  const [showLogins, setShowLogins] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/api/admin/users/${userId}/account`);
      setAcct(res.data.account);
      setHistory(res.data.history || []);
    } catch (err) {
      toast.error(err.cleanMessage || 'Failed to load account');
    } finally {
      setLoading(false);
    }
  }, [userId, toast]);

  useEffect(() => { if (userId) load(); }, [userId, load]);

  const refresh = () => { load(); onChange && onChange(); };

  const post = async (url, body, successMsg) => {
    setBusy(true);
    try {
      await api.post(url, body || {});
      toast.success(successMsg);
      setModal(null);
      refresh();
    } catch (err) {
      toast.error(err.cleanMessage || 'Action failed');
    } finally {
      setBusy(false);
    }
  };
  const patch = async (url, body, successMsg) => {
    setBusy(true);
    try {
      await api.patch(url, body);
      toast.success(successMsg);
      setModal(null);
      refresh();
    } catch (err) {
      toast.error(err.cleanMessage || 'Action failed');
    } finally {
      setBusy(false);
    }
  };

  const base = `/api/admin/users/${userId}`;

  const toggle2fa = async () => {
    try {
      await api.patch(`${base}/2fa`, { enabled: !acct.force_2fa });
      toast.success(acct.force_2fa ? '2FA disabled' : '2FA enforced');
      refresh();
    } catch (err) { toast.error(err.cleanMessage || 'Action failed'); }
  };

  const loadLogins = async () => {
    if (showLogins) { setShowLogins(false); return; }
    setShowLogins(true);
    try {
      const res = await api.get(`${base}/login-history`, { params: { limit: 25 } });
      setLogins(res.data || []);
    } catch (err) { toast.error(err.cleanMessage || 'Failed to load login history'); }
  };

  const submitModal = () => {
    const m = modal;
    const amount = parseFloat(m.amount);
    const note = m.note || undefined;
    switch (m.type) {
      case 'add': return post(`${base}/account/add-funds`, { amount, note }, 'Funds added');
      case 'remove': return post(`${base}/account/remove-funds`, { amount, note }, 'Funds removed');
      case 'balance': return patch(`${base}/account/balance`, { balance: amount, note }, 'Balance updated');
      case 'limit': return patch(`${base}/account/credit-limit`, { credit_limit: amount, note }, 'Credit limit updated');
      case 'block':
        return post(`${base}/block`, { reason_code: m.reason_code, reason: m.reason || undefined, notes: m.note || undefined }, 'User blocked');
      default: return undefined;
    }
  };

  if (loading || !acct) {
    return <div className="acct-panel"><Loader size={18} className="au-spin" /> Loading account…</div>;
  }

  return (
    <div className="acct-panel">
      <h4>
        <Wallet size={16} /> Account &amp; Balance
        <span style={{ marginLeft: 'auto' }}><StatusBadge status={acct.status} size="sm" /></span>
      </h4>

      <div className="acct-summary">
        <div className="acct-stat">
          <div className="acct-stat-label">Current Balance</div>
          <div className="acct-stat-value">{fmtMoney(acct.current_balance)}</div>
        </div>
        <div className="acct-stat">
          <div className="acct-stat-label">Credit Limit</div>
          <div className="acct-stat-value">{fmtMoney(acct.credit_limit)}</div>
        </div>
        <div className="acct-stat">
          <div className="acct-stat-label">Available Credit</div>
          <div className="acct-stat-value">{fmtMoney(acct.available_credit)}</div>
        </div>
        <div className="acct-stat">
          <div className="acct-stat-label">Spending Power</div>
          <div className="acct-stat-value">{fmtMoney(acct.spending_power)}</div>
        </div>
        <div className="acct-stat">
          <div className="acct-stat-label">Utilization</div>
          <div className="acct-stat-value">{(acct.credit_utilization || 0).toFixed(1)}%</div>
        </div>
        <div className="acct-stat">
          <div className="acct-stat-label">Total Spending</div>
          <div className="acct-stat-value">{fmtMoney(acct.total_spending)}</div>
        </div>
        <div className="acct-stat">
          <div className="acct-stat-label">Total Deposits</div>
          <div className="acct-stat-value">{fmtMoney(acct.total_deposits)}</div>
        </div>
      </div>

      <div className="acct-actions">
        <button className="acct-btn ok" onClick={() => setModal({ type: 'add', amount: '' })}><PlusCircle size={15} /> Add Funds</button>
        <button className="acct-btn warn" onClick={() => setModal({ type: 'remove', amount: '' })}><MinusCircle size={15} /> Remove Funds</button>
        <button className="acct-btn" onClick={() => setModal({ type: 'balance', amount: String(acct.current_balance) })}><Edit3 size={15} /> Set Balance</button>
        <button className="acct-btn" onClick={() => setModal({ type: 'limit', amount: String(acct.credit_limit) })}><CreditCard size={15} /> Credit Limit</button>
        <button className="acct-btn" onClick={() => post(`${base}/account/credit-suspend`, { enabled: !acct.credit_suspended }, acct.credit_suspended ? 'Credit resumed' : 'Credit suspended')}>
          <CreditCard size={15} /> {acct.credit_suspended ? 'Resume Credit' : 'Suspend Credit'}
        </button>
        <button className="acct-btn" onClick={() => post(`${base}/account/freeze`, { enabled: !acct.is_frozen }, acct.is_frozen ? 'Balance unfrozen' : 'Balance frozen')}>
          <Snowflake size={15} /> {acct.is_frozen ? 'Unfreeze' : 'Freeze'}
        </button>
        <button className="acct-btn" onClick={() => post(`${base}/account/reset`, {}, 'Balance reset')}><RotateCcw size={15} /> Reset</button>

        {acct.status === 'blocked' ? (
          <button className="acct-btn ok" onClick={() => post(`${base}/unblock`, { notes: 'Unblocked by admin' }, 'User unblocked')}><ShieldCheck size={15} /> Unblock</button>
        ) : (
          <button className="acct-btn danger" onClick={() => setModal({ type: 'block', reason_code: 'fraud', reason: '', note: '' })}><Ban size={15} /> Block User</button>
        )}
        <button className="acct-btn" onClick={() => setShowHistory((s) => !s)}><History size={15} /> History</button>
      </div>

      {showHistory && (
        <div style={{ marginTop: 14 }}>
          {history.length === 0 ? (
            <p style={{ color: '#94a3b8', fontSize: '0.85rem' }}>No account activity yet.</p>
          ) : (
            <ul className="acct-history">
              {history.map((h) => (
                <li key={h.id}>
                  <span className="acct-hist-type">{h.type.replace(/_/g, ' ')}</span>
                  {h.amount != null && <span className="acct-hist-amt">{fmtMoney(h.amount)}</span>}
                  <span className="acct-hist-when">{new Date(h.created_at).toLocaleString()}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* ── Security (2FA + login history) ── */}
      <div className="acct-security">
        <div className="acct-sec-row">
          <span className="acct-sec-label">
            <KeyRound size={15} /> Two-factor authentication
            <span className={`pill ${acct.force_2fa ? 'on' : 'off'}`} style={{ marginLeft: 8 }}>
              {acct.force_2fa ? 'Enforced' : 'Off'}
            </span>
          </span>
          <button className={`acct-btn ${acct.force_2fa ? 'warn' : 'ok'}`} onClick={toggle2fa}>
            {acct.force_2fa ? 'Disable 2FA' : 'Force 2FA'}
          </button>
        </div>
        <div className="acct-sec-row">
          <span className="acct-sec-label">
            {acct.email_verified ? <MailCheck size={15} /> : <MailX size={15} />} Email
            <span className={`pill ${acct.email_verified ? 'on' : 'off'}`} style={{ marginLeft: 8 }}>
              {acct.email_verified ? 'Verified' : 'Unverified'}
            </span>
          </span>
          <button className="acct-btn" onClick={loadLogins}><Monitor size={15} /> Login history</button>
        </div>

        {showLogins && (
          logins == null ? (
            <div style={{ padding: 10, color: '#94a3b8', fontSize: '0.84rem' }}><Loader size={14} className="au-spin" /> Loading…</div>
          ) : logins.length === 0 ? (
            <p style={{ color: '#94a3b8', fontSize: '0.85rem', marginTop: 8 }}>No login attempts recorded yet.</p>
          ) : (
            <ul className="acct-history" style={{ marginTop: 10 }}>
              {logins.map((l) => (
                <li key={l.id}>
                  <span className={`pill ${l.success ? 'on' : 'off'}`}>{l.success ? 'success' : 'failed'}</span>
                  <span className="acct-hist-type" style={{ textTransform: 'none' }}>{l.stage}{l.reason ? ` · ${l.reason}` : ''}</span>
                  <span style={{ color: '#94a3b8', fontSize: '0.76rem' }}>{l.ip || '—'}</span>
                  <span className="acct-hist-when">{new Date(l.created_at).toLocaleString()}</span>
                </li>
              ))}
            </ul>
          )
        )}
      </div>

      {/* ── Modal ── */}
      {modal && (
        <div className="modal-overlay" onClick={() => !busy && setModal(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            {modal.type === 'block' ? (
              <>
                <h3>Block user</h3>
                <p className="modal-sub">A blocked user cannot log in, transact, or modify their account.</p>
                <label>Reason</label>
                <select value={modal.reason_code} onChange={(e) => setModal({ ...modal, reason_code: e.target.value })}>
                  {BLOCK_REASONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
                {modal.reason_code === 'custom' && (
                  <>
                    <label>Custom reason</label>
                    <input value={modal.reason} onChange={(e) => setModal({ ...modal, reason: e.target.value })} placeholder="Describe the reason" />
                  </>
                )}
                <label>Notes (optional)</label>
                <textarea value={modal.note} onChange={(e) => setModal({ ...modal, note: e.target.value })} placeholder="Internal notes" />
                <div className="modal-actions">
                  <button className="btn-cancel" onClick={() => setModal(null)} disabled={busy}>Cancel</button>
                  <button className="btn-confirm danger" onClick={submitModal} disabled={busy}>{busy ? 'Blocking…' : 'Block user'}</button>
                </div>
              </>
            ) : (
              <>
                <h3>
                  {modal.type === 'add' && 'Add funds'}
                  {modal.type === 'remove' && 'Remove funds'}
                  {modal.type === 'balance' && 'Set balance'}
                  {modal.type === 'limit' && 'Set credit limit'}
                </h3>
                <p className="modal-sub">
                  {modal.type === 'add' && 'Deposits money into the user’s spendable balance.'}
                  {modal.type === 'remove' && 'Withdraws money from the user’s spendable balance.'}
                  {modal.type === 'balance' && 'Sets the user’s spendable balance to an exact figure.'}
                  {modal.type === 'limit' && 'Sets the user’s credit ceiling (separate from their balance).'}
                </p>
                <label>Amount ($)</label>
                <input
                  type="number" min="0" step="0.01" autoFocus
                  value={modal.amount}
                  onChange={(e) => setModal({ ...modal, amount: e.target.value })}
                />
                <label>Note (optional)</label>
                <input value={modal.note || ''} onChange={(e) => setModal({ ...modal, note: e.target.value })} placeholder="Reason for this change" />
                <div className="modal-actions">
                  <button className="btn-cancel" onClick={() => setModal(null)} disabled={busy}>Cancel</button>
                  <button className="btn-confirm" onClick={submitModal} disabled={busy || modal.amount === '' || isNaN(parseFloat(modal.amount))}>
                    {busy ? 'Saving…' : 'Confirm'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminAccountPanel;

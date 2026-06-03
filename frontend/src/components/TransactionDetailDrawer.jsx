import React, { useEffect, useState, useCallback } from 'react';
import { X, Loader, Save, AlertTriangle, ShieldCheck } from 'lucide-react';
import api from '../lib/api';
import { useToast } from '../contexts/ToastContext';
import './TransactionDetailDrawer.css';

// Canonical labels — shown in the UI as "Category".
const CATEGORY_OPTIONS = [
  'Food', 'Rent', 'Salary', 'Utilities', 'Entertainment',
  'Investment', 'Travel', 'Insurance', 'Other',
];

const fmtMoney = (v) =>
  v == null ? '—' : `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const fmtDate = (v) => (v ? new Date(v).toLocaleString() : '—');

const SeverityBadge = ({ severity }) => {
  if (!severity || severity === 'none') return null;
  return <span className={`tdd-sev tdd-sev-${severity}`}>{severity}</span>;
};

/**
 * Slide-in drawer showing full transaction detail. Allows editing tag /
 * category / description (PATCH /api/transactions/:id/tags).
 *
 * Props:
 *   transactionId  – id to load (drawer is open when this is truthy)
 *   onClose        – called to close
 *   onUpdated      – optional callback after a successful tag save
 *   canEdit        – whether to show the edit controls (default true)
 */
export const TransactionDetailDrawer = ({ transactionId, onClose, onUpdated, canEdit = true }) => {
  const toast = useToast();
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ merchant: '', tag: '', description: '' });

  const load = useCallback(async () => {
    if (!transactionId) return;
    setLoading(true);
    setError('');
    try {
      const res = await api.get(`/api/transactions/${transactionId}`);
      setDetail(res.data);
      setForm({
        merchant: res.data.merchant || '',
        tag: res.data.tag || '',
        description: res.data.description || '',
      });
    } catch (err) {
      setError(err.cleanMessage || 'Failed to load transaction');
    } finally {
      setLoading(false);
    }
  }, [transactionId]);

  useEffect(() => {
    load();
  }, [load]);

  // Close on Escape
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose?.();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const body = {};
      if (form.merchant !== '') body.merchant = form.merchant;
      if (form.tag) body.tag = form.tag;
      if (form.description !== '') body.description = form.description;
      const res = await api.patch(`/api/transactions/${transactionId}/tags`, body);
      setDetail(res.data);
      toast.success('Transaction updated');
      onUpdated?.(res.data);
    } catch (err) {
      toast.error(err.cleanMessage || 'Failed to update');
    } finally {
      setSaving(false);
    }
  };

  if (!transactionId) return null;

  const isFraud = detail?.is_fraud;

  return (
    <>
      <div className="tdd-overlay" onClick={onClose} />
      <aside className="tdd-drawer" role="dialog" aria-label="Transaction details">
        <header className="tdd-header">
          <h2>Transaction Details</h2>
          <button className="tdd-close" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </header>

        {loading ? (
          <div className="tdd-loading">
            <Loader className="tdd-spin" size={26} /> Loading…
          </div>
        ) : error ? (
          <div className="tdd-error">{error}</div>
        ) : detail ? (
          <div className="tdd-body">
            <div className={`tdd-status ${isFraud ? 'fraud' : 'ok'}`}>
              {isFraud ? <AlertTriangle size={20} /> : <ShieldCheck size={20} />}
              <span>{detail.fraud_status || (isFraud ? 'Fraud' : 'Approved')}</span>
              <SeverityBadge severity={detail.fraud_severity} />
            </div>

            {(detail.merchant || detail.description) && (
              <div className="tdd-merchant">{detail.merchant || detail.description}</div>
            )}
            <div className="tdd-amount">{fmtMoney(detail.amount)}</div>

            <dl className="tdd-grid">
              <div><dt>Name</dt><dd>{detail.merchant || '—'}</dd></div>
              <div><dt>Category</dt><dd>{detail.tag ? <span className="tdd-tag">{detail.tag}</span> : '—'}</dd></div>
              <div><dt>Transaction ID</dt><dd className="mono">{detail.transaction_id}</dd></div>
              <div><dt>User</dt><dd>{detail.username || '—'}{detail.user_email ? ` (${detail.user_email})` : ''}</dd></div>
              <div><dt>User ID</dt><dd className="mono">{detail.user_id || '—'}</dd></div>
              <div><dt>Date / Time</dt><dd>{fmtDate(detail.transaction_time || detail.created_at)}</dd></div>
              <div><dt>Fraud Score</dt><dd>{detail.fraud_score == null ? '—' : Number(detail.fraud_score).toFixed(4)}</dd></div>
              <div><dt>Creation Source</dt><dd>{(detail.creation_source || 'csv_upload').replace('_', ' ')}</dd></div>
            </dl>

            {detail.description && (
              <div className="tdd-desc">
                <dt>Description</dt>
                <p>{detail.description}</p>
              </div>
            )}

            {detail.metadata && Object.keys(detail.metadata).length > 0 && (
              <details className="tdd-meta">
                <summary>Additional metadata</summary>
                <pre>{JSON.stringify(detail.metadata, null, 2)}</pre>
              </details>
            )}

            {canEdit && (
              <div className="tdd-edit">
                <h3>Edit details</h3>
                <label>
                  Name (business)
                  <input
                    type="text"
                    value={form.merchant}
                    placeholder="e.g. Woolworths"
                    onChange={(e) => setForm((f) => ({ ...f, merchant: e.target.value }))}
                  />
                </label>
                <label>
                  Category
                  <select
                    value={form.tag}
                    onChange={(e) => setForm((f) => ({ ...f, tag: e.target.value }))}
                  >
                    <option value="">— none —</option>
                    {CATEGORY_OPTIONS.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Description
                  <textarea
                    rows={3}
                    value={form.description}
                    placeholder="Optional notes"
                    onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  />
                </label>
                <button className="tdd-save" onClick={handleSave} disabled={saving}>
                  {saving ? <Loader className="tdd-spin" size={16} /> : <Save size={16} />}
                  {saving ? 'Saving…' : 'Save changes'}
                </button>
              </div>
            )}
          </div>
        ) : null}
      </aside>
    </>
  );
};

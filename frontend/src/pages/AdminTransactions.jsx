import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus, Trash2, Upload, Loader, Users, ClipboardList, Send, AlertCircle, CheckCircle,
} from 'lucide-react';
import api from '../lib/api';
import { Sidebar } from '../components/Sidebar';
import { TopBar } from '../components/TopBar';
import { useToast } from '../contexts/ToastContext';
import './AdminTransactions.css';

const TAG_OPTIONS = [
  'Food', 'Rent', 'Salary', 'Utilities', 'Entertainment',
  'Investment', 'Travel', 'Insurance', 'Other',
];

const emptyRow = () => ({
  amount: '',
  category: '',
  tag: '',
  description: '',
  is_fraud_override: '',
});

export const AdminTransactions = () => {
  const toast = useToast();
  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [selectedUser, setSelectedUser] = useState('');
  const [mode, setMode] = useState('form'); // 'form' | 'bulk'
  const [rows, setRows] = useState([emptyRow()]);
  const [bulkText, setBulkText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  const loadUsers = useCallback(async () => {
    setUsersLoading(true);
    try {
      const res = await api.get('/api/admin/users');
      setUsers(res.data || []);
    } catch (err) {
      toast.error(err.cleanMessage || 'Failed to load users');
    } finally {
      setUsersLoading(false);
    }
  }, [toast]);

  useEffect(() => { loadUsers(); }, [loadUsers]);

  const updateRow = (idx, field, value) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, [field]: value } : r)));
  };
  const addRow = () => setRows((prev) => [...prev, emptyRow()]);
  const removeRow = (idx) => setRows((prev) => prev.filter((_, i) => i !== idx));

  // Parse bulk CSV-ish text: amount,category,tag,description[,fraud]
  const parseBulk = () => {
    const lines = bulkText.split('\n').map((l) => l.trim()).filter(Boolean);
    const parsed = [];
    const errors = [];
    lines.forEach((line, i) => {
      const parts = line.split(',').map((p) => p.trim());
      const amount = parseFloat(parts[0]);
      if (isNaN(amount)) {
        errors.push(`Line ${i + 1}: invalid amount "${parts[0]}"`);
        return;
      }
      parsed.push({
        amount: String(amount),
        category: parts[1] || '',
        tag: TAG_OPTIONS.includes(parts[2]) ? parts[2] : '',
        description: parts[3] || '',
        is_fraud_override: (parts[4] || '').toLowerCase() === 'fraud' ? 'true' : '',
      });
    });
    if (errors.length) {
      toast.error(errors.join(' • '));
    }
    if (parsed.length) {
      setRows(parsed);
      setMode('form');
      toast.success(`Parsed ${parsed.length} transaction(s) — review and submit`);
    }
  };

  const buildPayload = () => {
    const transactions = [];
    for (const r of rows) {
      const amount = parseFloat(r.amount);
      if (isNaN(amount) || amount < 0) continue;
      const tx = { amount };
      if (r.category) tx.category = r.category;
      if (r.tag) tx.tag = r.tag;
      if (r.description) tx.description = r.description;
      if (r.is_fraud_override === 'true') tx.is_fraud_override = true;
      if (r.is_fraud_override === 'false') tx.is_fraud_override = false;
      transactions.push(tx);
    }
    return transactions;
  };

  const handleSubmit = async () => {
    if (!selectedUser) { toast.warning('Select a target user first'); return; }
    const transactions = buildPayload();
    if (transactions.length === 0) {
      toast.warning('Add at least one transaction with a valid amount');
      return;
    }
    setSubmitting(true);
    setResult(null);
    try {
      const res = await api.post('/api/admin/transactions/bulk', {
        user_id: selectedUser,
        transactions,
      });
      setResult(res.data);
      if (res.data.success) {
        toast.success(
          `Created ${res.data.created_count} transaction(s)` +
          (res.data.fraud_flagged ? ` — ${res.data.fraud_flagged} flagged as fraud` : '')
        );
        setRows([emptyRow()]);
        loadUsers();
      } else {
        toast.error('No transactions were created');
      }
    } catch (err) {
      toast.error(err.cleanMessage || 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <TopBar
          title="Transaction Management"
          subtitle="Create transactions on behalf of a user — individually or in bulk"
        />

        <div className="at-card">
          <label className="at-field">
            <span className="at-label"><Users size={15} /> Target user</span>
            <select
              value={selectedUser}
              onChange={(e) => setSelectedUser(e.target.value)}
              disabled={usersLoading}
            >
              <option value="">{usersLoading ? 'Loading users…' : 'Select a user…'}</option>
              {users.map((u) => (
                <option key={u.user_id} value={u.user_id}>
                  {u.username} ({u.email}) — {u.total_transactions} tx
                </option>
              ))}
            </select>
          </label>

          <div className="at-tabs">
            <button className={mode === 'form' ? 'active' : ''} onClick={() => setMode('form')}>
              <ClipboardList size={15} /> Individual entry
            </button>
            <button className={mode === 'bulk' ? 'active' : ''} onClick={() => setMode('bulk')}>
              <Upload size={15} /> Bulk paste
            </button>
          </div>

          {mode === 'bulk' ? (
            <div className="at-bulk">
              <p className="at-hint">
                One transaction per line: <code>amount, category, tag, description, [fraud]</code>
                <br />Example: <code>1299.00, Electronics, Entertainment, New laptop, fraud</code>
              </p>
              <textarea
                rows={8}
                value={bulkText}
                onChange={(e) => setBulkText(e.target.value)}
                placeholder={'250.00, Groceries, Food, Weekly shop\n5400.00, Wire, Investment, Large transfer, fraud'}
              />
              <button className="at-secondary" onClick={parseBulk}>
                <ClipboardList size={16} /> Parse into rows
              </button>
            </div>
          ) : (
            <div className="at-rows">
              <div className="at-row at-row-head">
                <span>Amount ($)</span>
                <span>Category</span>
                <span>Tag</span>
                <span>Description</span>
                <span>Fraud?</span>
                <span />
              </div>
              {rows.map((r, idx) => (
                <div className="at-row" key={idx}>
                  <input
                    type="number" min="0" step="0.01" placeholder="0.00"
                    value={r.amount} onChange={(e) => updateRow(idx, 'amount', e.target.value)}
                  />
                  <input
                    type="text" placeholder="e.g. Groceries"
                    value={r.category} onChange={(e) => updateRow(idx, 'category', e.target.value)}
                  />
                  <select value={r.tag} onChange={(e) => updateRow(idx, 'tag', e.target.value)}>
                    <option value="">—</option>
                    {TAG_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <input
                    type="text" placeholder="Optional notes"
                    value={r.description} onChange={(e) => updateRow(idx, 'description', e.target.value)}
                  />
                  <select value={r.is_fraud_override} onChange={(e) => updateRow(idx, 'is_fraud_override', e.target.value)}>
                    <option value="">Auto</option>
                    <option value="true">Fraud</option>
                    <option value="false">Legit</option>
                  </select>
                  <button
                    className="at-remove" onClick={() => removeRow(idx)}
                    disabled={rows.length === 1} aria-label="Remove row"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))}
              <button className="at-secondary" onClick={addRow}>
                <Plus size={16} /> Add row
              </button>
            </div>
          )}

          <div className="at-actions">
            <button className="at-primary" onClick={handleSubmit} disabled={submitting}>
              {submitting ? <Loader size={17} className="at-spin" /> : <Send size={17} />}
              {submitting ? 'Submitting…' : 'Submit transactions'}
            </button>
          </div>

          {result && (
            <div className={`at-result ${result.success ? 'ok' : 'err'}`}>
              {result.success ? <CheckCircle size={18} /> : <AlertCircle size={18} />}
              <div>
                <strong>
                  {result.created_count} created
                  {result.fraud_flagged > 0 && `, ${result.fraud_flagged} flagged as fraud`}
                  {result.failed_count > 0 && `, ${result.failed_count} failed`}
                </strong>
                {result.errors?.length > 0 && (
                  <ul className="at-errors">
                    {result.errors.map((e, i) => (
                      <li key={i}>Row {e.index}: {e.error}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

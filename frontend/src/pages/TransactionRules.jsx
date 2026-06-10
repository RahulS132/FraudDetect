import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus, Power, Trash2, Edit2, ShieldOff, Loader, Filter,
} from 'lucide-react';
import api from '../lib/api';
import { Sidebar } from '../components/Sidebar';
import { TopBar } from '../components/TopBar';
import { useToast } from '../contexts/ToastContext';
import './AdminPages.css';

const RULE_TYPES = [
  { value: 'merchant', label: 'Merchant name' },
  { value: 'category', label: 'Merchant category' },
  { value: 'amount_range', label: 'Amount range' },
  { value: 'country', label: 'Country' },
  { value: 'card_type', label: 'Card type' },
  { value: 'user', label: 'Specific user' },
];

const emptyForm = { name: '', rule_type: 'merchant', action: 'block', enabled: true, value: '', min: '', max: '', user_id: '', description: '' };

const buildConfig = (f) => {
  switch (f.rule_type) {
    case 'amount_range': {
      const c = {};
      if (f.min !== '') c.min = parseFloat(f.min);
      if (f.max !== '') c.max = parseFloat(f.max);
      return c;
    }
    case 'user': return { user_id: f.user_id };
    default: {
      // allow comma-separated list
      const vals = f.value.split(',').map((v) => v.trim()).filter(Boolean);
      return vals.length > 1 ? { values: vals } : { value: vals[0] || '' };
    }
  }
};

const describeConfig = (r) => {
  const c = r.config || {};
  if (r.rule_type === 'amount_range') {
    const lo = c.min != null ? `$${c.min}` : '—';
    const hi = c.max != null ? `$${c.max}` : '∞';
    return `${lo} to ${hi}`;
  }
  if (r.rule_type === 'user') return c.user_id || '—';
  return c.values ? c.values.join(', ') : (c.value || '—');
};

export const TransactionRules = () => {
  const toast = useToast();
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState('');
  const [modal, setModal] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/admin/transaction-rules');
      setRules(res.data || []);
    } catch (err) {
      toast.error(err.cleanMessage || 'Failed to load rules');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    const f = modal;
    if (!f.name.trim()) { toast.error('Name is required'); return; }
    setBusy(true);
    const body = {
      name: f.name, rule_type: f.rule_type, action: f.action,
      enabled: f.enabled, config: buildConfig(f), description: f.description || undefined,
    };
    try {
      if (f.id) await api.patch(`/api/admin/transaction-rules/${f.id}`, body);
      else await api.post('/api/admin/transaction-rules', body);
      toast.success(f.id ? 'Rule updated' : 'Rule created');
      setModal(null);
      load();
    } catch (err) {
      toast.error(err.cleanMessage || 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (r) => {
    try { await api.post(`/api/admin/transaction-rules/${r.id}/toggle`); load(); }
    catch (err) { toast.error(err.cleanMessage || 'Toggle failed'); }
  };
  const remove = async (r) => {
    if (!window.confirm(`Delete rule "${r.name}"?`)) return;
    try { await api.delete(`/api/admin/transaction-rules/${r.id}`); toast.success('Rule deleted'); load(); }
    catch (err) { toast.error(err.cleanMessage || 'Delete failed'); }
  };

  const edit = (r) => {
    const c = r.config || {};
    setModal({
      id: r.id, name: r.name, rule_type: r.rule_type, action: r.action, enabled: r.enabled,
      value: c.values ? c.values.join(', ') : (c.value || ''),
      min: c.min != null ? String(c.min) : '', max: c.max != null ? String(c.max) : '',
      user_id: c.user_id || '', description: r.description || '',
    });
  };

  const shown = typeFilter ? rules.filter((r) => r.rule_type === typeFilter) : rules;

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <TopBar title="Transaction Rules" subtitle="Block or flag transactions before they are processed" />
        <div className="adm-wrap">
          <div className="adm-toolbar">
            <div className="adm-search" style={{ flex: '0 0 auto' }}>
              <Filter size={15} />
              <select className="adm-select" style={{ border: 'none', padding: 0 }} value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
                <option value="">All types</option>
                {RULE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
            <div style={{ flex: 1 }} />
            <button className="adm-btn" onClick={() => setModal({ ...emptyForm })}><Plus size={16} /> Create Rule</button>
          </div>

          <div className="adm-card">
            {loading ? (
              <div className="adm-state"><Loader size={18} className="au-spin" /> Loading rules…</div>
            ) : shown.length === 0 ? (
              <div className="empty-rules">
                <ShieldOff size={42} />
                <h3>No rules yet</h3>
                <p>Create a rule to automatically block or flag matching transactions.</p>
              </div>
            ) : (
              <table className="adm-table">
                <thead>
                  <tr>
                    <th>Name</th><th>Type</th><th>Match</th><th>Action</th>
                    <th>Status</th><th>Triggered</th><th></th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((r) => (
                    <tr key={r.id}>
                      <td><strong>{r.name}</strong>{r.description && <div style={{ color: '#94a3b8', fontSize: '0.78rem' }}>{r.description}</div>}</td>
                      <td>{RULE_TYPES.find((t) => t.value === r.rule_type)?.label || r.rule_type}</td>
                      <td><span className="kv">{describeConfig(r)}</span></td>
                      <td><span className={`pill ${r.action}`}>{r.action}</span></td>
                      <td><span className={`pill ${r.enabled ? 'on' : 'off'}`}>{r.enabled ? 'Enabled' : 'Disabled'}</span></td>
                      <td>{r.trigger_count}×</td>
                      <td>
                        <div className="adm-row-actions">
                          <button className="icon-btn" title={r.enabled ? 'Disable' : 'Enable'} onClick={() => toggle(r)}><Power size={15} /></button>
                          <button className="icon-btn" title="Edit" onClick={() => edit(r)}><Edit2 size={15} /></button>
                          <button className="icon-btn danger" title="Delete" onClick={() => remove(r)}><Trash2 size={15} /></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {modal && (
          <div className="modal-overlay" onClick={() => !busy && setModal(null)}>
            <div className="modal" onClick={(e) => e.stopPropagation()}>
              <h3>{modal.id ? 'Edit rule' : 'Create rule'}</h3>
              <p className="modal-sub">Matching transactions will be {modal.action === 'block' ? 'rejected' : 'flagged for review'}.</p>

              <label>Rule name</label>
              <input value={modal.name} onChange={(e) => setModal({ ...modal, name: e.target.value })} placeholder="e.g. Block high-risk merchants" />

              <label>Rule type</label>
              <select value={modal.rule_type} onChange={(e) => setModal({ ...modal, rule_type: e.target.value })}>
                {RULE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>

              {modal.rule_type === 'amount_range' ? (
                <div style={{ display: 'flex', gap: 10 }}>
                  <div style={{ flex: 1 }}>
                    <label>Min ($)</label>
                    <input type="number" value={modal.min} onChange={(e) => setModal({ ...modal, min: e.target.value })} placeholder="0" />
                  </div>
                  <div style={{ flex: 1 }}>
                    <label>Max ($)</label>
                    <input type="number" value={modal.max} onChange={(e) => setModal({ ...modal, max: e.target.value })} placeholder="∞" />
                  </div>
                </div>
              ) : modal.rule_type === 'user' ? (
                <>
                  <label>User ID</label>
                  <input value={modal.user_id} onChange={(e) => setModal({ ...modal, user_id: e.target.value })} placeholder="Mongo user id" />
                </>
              ) : (
                <>
                  <label>Value(s) — comma-separated for multiple</label>
                  <input value={modal.value} onChange={(e) => setModal({ ...modal, value: e.target.value })} placeholder="e.g. amazon, ebay" />
                </>
              )}

              <label>Action</label>
              <select value={modal.action} onChange={(e) => setModal({ ...modal, action: e.target.value })}>
                <option value="block">Block transaction</option>
                <option value="flag">Flag for review</option>
              </select>

              <label>Description (optional)</label>
              <input value={modal.description} onChange={(e) => setModal({ ...modal, description: e.target.value })} />

              <div className="modal-actions">
                <button className="btn-cancel" onClick={() => setModal(null)} disabled={busy}>Cancel</button>
                <button className="btn-confirm" onClick={save} disabled={busy}>{busy ? 'Saving…' : modal.id ? 'Save changes' : 'Create rule'}</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default TransactionRules;

import React, { useState, useEffect, useCallback } from 'react';
import { Search, Loader, ScrollText, ChevronLeft, ChevronRight } from 'lucide-react';
import api from '../lib/api';
import { Sidebar } from '../components/Sidebar';
import { TopBar } from '../components/TopBar';
import { useToast } from '../contexts/ToastContext';
import './AdminPages.css';

const fmtTime = (t) => (t ? new Date(t).toLocaleString() : '');

const ACTIONS = [
  '', 'user_blocked', 'user_unblocked', 'user_status_changed',
  'balance_add_funds', 'balance_remove_funds', 'balance_set', 'credit_limit_change',
  'balance_freeze', 'balance_unfreeze', 'balance_reset',
  'fraud_threshold_changed', 'transaction_rule_created', 'transaction_rule_updated',
  'transaction_rule_deleted', 'transaction_rule_toggled',
  'bulk_create_transactions', 'bulk_create_rejected',
];

const summarizeDetails = (d) => {
  if (!d || typeof d !== 'object') return '';
  if (d.before && d.after) {
    const b = d.before, a = d.after;
    if (b.current_balance != null && a.current_balance != null && b.current_balance !== a.current_balance)
      return `balance $${b.current_balance} → $${a.current_balance}`;
    if (b.credit_limit != null && a.credit_limit != null && b.credit_limit !== a.credit_limit)
      return `limit $${b.credit_limit} → $${a.credit_limit}`;
  }
  if (d.reason_code) return `reason: ${d.reason_code}`;
  if (d.count != null) return `${d.count} txn, ${d.fraud_flagged || 0} fraud, ${d.rejected || 0} rejected`;
  if (d.name) return d.name;
  const keys = Object.keys(d);
  return keys.length ? keys.slice(0, 3).map((k) => `${k}=${JSON.stringify(d[k])}`).join(', ') : '';
};

export const AuditLog = () => {
  const toast = useToast();
  const [data, setData] = useState({ items: [], total: 0, page: 1, total_pages: 0 });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [action, setAction] = useState('');
  const [page, setPage] = useState(1);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/api/admin/audit-logs/search', {
        params: { page, page_size: 25, search: search || undefined, action: action || undefined },
      });
      setData(res.data);
    } catch (err) {
      toast.error(err.cleanMessage || 'Failed to load audit log');
    } finally {
      setLoading(false);
    }
  }, [page, search, action, toast]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => { setPage(1); }, [search, action]);

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <TopBar title="Security Audit Log" subtitle="Every privileged admin action, with before/after values" />
        <div className="adm-wrap">
          <div className="adm-toolbar">
            <div className="adm-search">
              <Search size={15} />
              <input placeholder="Search action or admin email…" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <select className="adm-select" value={action} onChange={(e) => setAction(e.target.value)}>
              {ACTIONS.map((a) => <option key={a} value={a}>{a ? a.replace(/_/g, ' ') : 'All actions'}</option>)}
            </select>
          </div>

          <div className="adm-card">
            {loading ? (
              <div className="adm-state"><Loader size={18} className="au-spin" /> Loading…</div>
            ) : data.items.length === 0 ? (
              <div className="empty-rules"><ScrollText size={42} /><h3>No audit entries</h3><p>Admin actions will appear here.</p></div>
            ) : (
              <>
                <table className="adm-table">
                  <thead>
                    <tr><th>When</th><th>Action</th><th>Admin</th><th>Target user</th><th>Details</th></tr>
                  </thead>
                  <tbody>
                    {data.items.map((e) => (
                      <tr key={e.id}>
                        <td style={{ whiteSpace: 'nowrap' }}>{fmtTime(e.created_at)}</td>
                        <td><span className="kv">{e.action}</span></td>
                        <td>{e.actor_email || e.actor_id || 'system'}</td>
                        <td>{e.target_username || e.target_user_id || '—'}</td>
                        <td style={{ color: '#64748b', fontSize: '0.82rem' }}>{summarizeDetails(e.details)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="adm-pagination">
                  <span>{data.total} entries · page {data.page} of {data.total_pages || 1}</span>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}><ChevronLeft size={14} /> Prev</button>
                    <button disabled={page >= (data.total_pages || 1)} onClick={() => setPage((p) => p + 1)}>Next <ChevronRight size={14} /></button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default AuditLog;

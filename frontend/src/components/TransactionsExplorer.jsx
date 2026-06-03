import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Search, ChevronLeft, ChevronRight, ArrowUp, ArrowDown,
  Filter, Inbox, AlertTriangle,
} from 'lucide-react';
import api from '../lib/api';
import { useRealtime } from '../contexts/RealtimeContext';
import { TransactionDetailDrawer } from './TransactionDetailDrawer';
import './TransactionsExplorer.css';

// Canonical labels — shown in the UI as "Category".
const CATEGORY_OPTIONS = [
  'Food', 'Rent', 'Salary', 'Utilities', 'Entertainment',
  'Investment', 'Travel', 'Insurance', 'Other',
];

const fmtMoney = (v) =>
  v == null ? '—' : `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const fmtDate = (v) => (v ? new Date(v).toLocaleDateString() : '—');

/**
 * Reusable, self-fetching transactions browser.
 *
 * Props:
 *   endpoint   – API path returning a TransactionListResponse
 *                (default '/api/transactions/search'; admin per-user views pass
 *                 '/api/admin/users/:id/transactions')
 *   title      – optional heading
 *   compact    – hide the free-text/amount/date filters (used in admin user view)
 *   showUser   – show the User column (admin/global views)
 */
export const TransactionsExplorer = ({
  endpoint = '/api/transactions/search',
  title,
  compact = false,
  showUser = false,
  initialFraudStatus = '',   // '' | 'fraud' | 'approved'
}) => {
  const { onTransactionsUpdated } = useRealtime();

  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  // Start as not-loading so the table renders immediately rather than a
  // full-panel "Loading…" placeholder. A subtle inline bar shows on refetches.
  const [loading, setLoading] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [error, setError] = useState('');

  const [q, setQ] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [tag, setTag] = useState('');
  const [fraudStatus, setFraudStatus] = useState(initialFraudStatus);
  const [minAmount, setMinAmount] = useState('');
  const [maxAmount, setMaxAmount] = useState('');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortDir, setSortDir] = useState('desc');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [selectedId, setSelectedId] = useState(null);

  // Debounce the free-text query.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 350);
    return () => clearTimeout(t);
  }, [q]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const params = {
        page, page_size: pageSize, sort_by: sortBy, sort_dir: sortDir,
      };
      if (debouncedQ) params.q = debouncedQ;
      if (tag) params.tag = tag;
      if (fraudStatus) params.fraud_status = fraudStatus;
      if (minAmount !== '') params.min_amount = minAmount;
      if (maxAmount !== '') params.max_amount = maxAmount;
      const res = await api.get(endpoint, { params });
      setItems(res.data.items || []);
      setTotal(res.data.total || 0);
      setTotalPages(res.data.total_pages || 0);
    } catch (err) {
      setError(err.cleanMessage || 'Failed to load transactions');
    } finally {
      setLoading(false);
      setHasLoaded(true);
    }
  }, [endpoint, page, pageSize, sortBy, sortDir, debouncedQ, tag, fraudStatus, minAmount, maxAmount]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Reset to page 1 when filters change.
  useEffect(() => {
    setPage(1);
  }, [debouncedQ, tag, fraudStatus, minAmount, maxAmount, sortBy, sortDir]);

  // Live refresh when transactions change anywhere relevant.
  useEffect(() => {
    const unsub = onTransactionsUpdated(() => fetchData());
    return unsub;
  }, [onTransactionsUpdated, fetchData]);

  const toggleSort = (field) => {
    if (sortBy === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortBy(field);
      setSortDir('desc');
    }
  };

  const SortIcon = ({ field }) => {
    if (sortBy !== field) return null;
    return sortDir === 'asc' ? <ArrowUp size={13} /> : <ArrowDown size={13} />;
  };

  return (
    <div className="txe">
      {title && <h3 className="txe-title">{title}</h3>}

      <div className="txe-filters">
        {!compact && (
          <div className="txe-search">
            <Search size={16} />
            <input
              type="text"
              placeholder="Search business, user, category, description, amount…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
        )}

        <select value={tag} onChange={(e) => setTag(e.target.value)} className="txe-select">
          <option value="">All categories</option>
          {CATEGORY_OPTIONS.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>

        <select value={fraudStatus} onChange={(e) => setFraudStatus(e.target.value)} className="txe-select">
          <option value="">All statuses</option>
          <option value="fraud">Fraud</option>
          <option value="approved">Approved</option>
        </select>

        {!compact && (
          <>
            <input
              className="txe-amount" type="number" min="0" placeholder="Min $"
              value={minAmount} onChange={(e) => setMinAmount(e.target.value)}
            />
            <input
              className="txe-amount" type="number" min="0" placeholder="Max $"
              value={maxAmount} onChange={(e) => setMaxAmount(e.target.value)}
            />
          </>
        )}
        <span className="txe-count"><Filter size={14} /> {total} result{total === 1 ? '' : 's'}</span>
      </div>

      {error ? (
        <div className="txe-state txe-error"><AlertTriangle size={22} /> {error}</div>
      ) : hasLoaded && items.length === 0 ? (
        <div className="txe-state"><Inbox size={28} /> No transactions match your filters.</div>
      ) : (
        <div className="txe-table-wrap">
          {loading && <div className="txe-loadbar" aria-label="Loading" />}
          <table className="txe-table">
            <thead>
              <tr>
                <th>Name</th>
                {showUser && <th>User</th>}
                <th className="sortable" onClick={() => toggleSort('amount')}>
                  Amount <SortIcon field="amount" />
                </th>
                <th>Category</th>
                <th className="sortable" onClick={() => toggleSort('fraud_score')}>
                  Score <SortIcon field="fraud_score" />
                </th>
                <th>Status</th>
                <th className="sortable" onClick={() => toggleSort('created_at')}>
                  Date <SortIcon field="created_at" />
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((tx) => (
                <tr key={tx.transaction_id} className="txe-row" onClick={() => setSelectedId(tx.transaction_id)}>
                  <td className="txe-name">
                    {tx.merchant || tx.description || (
                      <span className="mono txe-id">{tx.transaction_id.slice(-8)}</span>
                    )}
                  </td>
                  {showUser && <td>{tx.username || tx.user_id?.slice(-6) || '—'}</td>}
                  <td className="txe-amt">{fmtMoney(tx.amount)}</td>
                  <td>{tx.tag ? <span className="txe-tag">{tx.tag}</span> : <span className="txe-muted">—</span>}</td>
                  <td>{tx.fraud_score == null ? '—' : Number(tx.fraud_score).toFixed(3)}</td>
                  <td>
                    <span className={`txe-status ${tx.is_fraud ? 'fraud' : 'ok'}`}>
                      {tx.is_fraud ? 'Fraud' : 'Approved'}
                    </span>
                  </td>
                  <td className="txe-muted">{fmtDate(tx.transaction_time || tx.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="txe-pager">
          <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            <ChevronLeft size={16} /> Prev
          </button>
          <span>Page {page} of {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Next <ChevronRight size={16} />
          </button>
        </div>
      )}

      <TransactionDetailDrawer
        transactionId={selectedId}
        onClose={() => setSelectedId(null)}
        onUpdated={() => fetchData()}
      />
    </div>
  );
};

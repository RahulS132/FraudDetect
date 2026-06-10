import React, { useState, useEffect, useCallback } from 'react';
import { Wallet, CreditCard, Snowflake } from 'lucide-react';
import api from '../lib/api';
import { useRealtime } from '../contexts/RealtimeContext';
import { StatusBadge } from './StatusBadge';
import './Account.css';

const fmtMoney = (v) =>
  v == null ? '$0.00' : `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/**
 * User-facing balance / credit widgets. Fetches the caller's own account
 * (`/api/account/me`) and live-refreshes when transactions change.
 */
export const BalanceWidgets = () => {
  const [acct, setAcct] = useState(null);
  const { onTransactionsUpdated } = useRealtime();

  const load = useCallback(async () => {
    try {
      const res = await api.get('/api/account/me');
      setAcct(res.data);
    } catch {
      /* non-fatal — dashboard still renders without balance */
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => onTransactionsUpdated(() => load()), [onTransactionsUpdated, load]);

  if (!acct) return null;

  const util = Math.min(100, Math.max(0, acct.credit_utilization || 0));
  const utilClass = util < 50 ? 'low' : util < 80 ? 'med' : 'high';

  return (
    <div className="balance-grid">
      <div className="balance-hero">
        <div className="balance-hero-top">
          <div>
            <div className="balance-hero-label">Current Balance</div>
            <div className="balance-hero-value">{fmtMoney(acct.current_balance)}</div>
          </div>
          <StatusBadge status={acct.status} />
        </div>
        <div className="balance-hero-sub">
          <div>
            <span className="balance-hero-sub-label">Credit Limit</span>
            <span className="balance-hero-sub-value">{fmtMoney(acct.credit_limit)}</span>
          </div>
          <div>
            <span className="balance-hero-sub-label">Available Credit</span>
            <span className="balance-hero-sub-value">{fmtMoney(acct.available_credit)}</span>
          </div>
        </div>
        {acct.is_frozen && (
          <span className="balance-frozen-note"><Snowflake size={13} /> Balance frozen</span>
        )}
        {acct.credit_suspended && !acct.is_frozen && (
          <span className="balance-frozen-note"><CreditCard size={13} /> Credit suspended</span>
        )}
      </div>

      <div className="util-card">
        <div className="util-title">Credit Utilization</div>
        <div className="util-pct">{util.toFixed(1)}%</div>
        <div className="util-bar">
          <div className={`util-fill ${utilClass}`} style={{ width: `${util}%` }} />
        </div>
        <div className="util-meta">
          <span>{fmtMoney(acct.current_balance)} used</span>
          <span>{fmtMoney(acct.available_credit)} left</span>
        </div>
      </div>

      <div className="balance-mini">
        <div className="mini-row">
          <span className="mini-label"><Wallet size={14} style={{ verticalAlign: -2, marginRight: 6 }} />Total Spending</span>
          <span className="mini-value">{fmtMoney(acct.total_spending)}</span>
        </div>
        <div className="mini-row">
          <span className="mini-label">Total Deposits</span>
          <span className="mini-value">{fmtMoney(acct.total_deposits)}</span>
        </div>
        <div className="mini-row">
          <span className="mini-label">Total Transactions</span>
          <span className="mini-value">{acct.total_transactions}</span>
        </div>
      </div>
    </div>
  );
};

export default BalanceWidgets;

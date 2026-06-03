import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { Sidebar } from '../components/Sidebar';
import { TopBar } from '../components/TopBar';
import { TransactionsExplorer } from '../components/TransactionsExplorer';
import { useAuth } from '../contexts/AuthContext';
import './Transactions.css';

/**
 * Searchable transactions page.
 *   • Users see and search only their own transactions.
 *   • Admins search across all transactions (User column shown).
 * The backend auto-scopes /api/transactions/search by role, so the same
 * component serves both — we only toggle the User column.
 *
 * Accepts a ?filter= query param (fraud | approved) so the dashboard stat
 * cards can deep-link straight into a filtered view.
 */
export const Transactions = () => {
  const { isAdmin } = useAuth();
  const admin = isAdmin();
  const [params] = useSearchParams();
  const filter = params.get('filter');
  const initialFraudStatus =
    filter === 'fraud' ? 'fraud' : filter === 'approved' ? 'approved' : '';

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <TopBar
          title="Transactions"
          subtitle={admin ? 'Search and inspect every transaction in the system' : 'Search and review your transactions'}
        />
        <div className="tx-page-card">
          <TransactionsExplorer
            key={initialFraudStatus || 'all'}
            endpoint="/api/transactions/search"
            showUser={admin}
            initialFraudStatus={initialFraudStatus}
          />
        </div>
      </div>
    </div>
  );
};

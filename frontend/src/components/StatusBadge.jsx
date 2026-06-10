import React from 'react';
import './Account.css';

/**
 * Account status pill. Renders one of: active / suspended / blocked /
 * under_review with a colour-coded style.
 */
const LABELS = {
  active: 'Active',
  suspended: 'Suspended',
  blocked: 'Blocked',
  under_review: 'Under Review',
};

export const StatusBadge = ({ status, size }) => {
  const key = (status || 'active').toLowerCase();
  return (
    <span className={`status-badge status-${key} ${size === 'sm' ? 'status-sm' : ''}`}>
      <span className="status-dot" />
      {LABELS[key] || status}
    </span>
  );
};

export default StatusBadge;

import React from 'react';
import { NotificationCenter } from './NotificationCenter';
import './TopBar.css';

/**
 * Page header bar with a title/subtitle on the left and the live
 * NotificationCenter bell on the right. Used on every authenticated page so the
 * notification dropdown is always reachable.
 */
export const TopBar = ({ title, subtitle, children }) => (
  <div className="topbar">
    <div className="topbar-titles">
      <h1 className="page-title">{title}</h1>
      {subtitle && <p className="page-subtitle">{subtitle}</p>}
    </div>
    <div className="topbar-actions">
      {children}
      <NotificationCenter />
    </div>
  </div>
);

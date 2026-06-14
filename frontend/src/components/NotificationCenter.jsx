import React, { useState, useRef, useEffect } from 'react';
import { Bell, Check, AlertTriangle, ShieldAlert, Info } from 'lucide-react';
import { useRealtime } from '../contexts/RealtimeContext';
import './NotificationCenter.css';

const severityIcon = (severity) => {
  if (severity === 'critical' || severity === 'high') return ShieldAlert;
  if (severity === 'medium' || severity === 'low') return AlertTriangle;
  return Info;
};

const timeAgo = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  const secs = Math.floor((Date.now() - d.getTime()) / 1000);
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return d.toLocaleDateString();
};

export const NotificationCenter = () => {
  const { notifications, unreadCount, markRead, markAllRead, connected } = useRealtime();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    // Only listen while open, and on the next tick so the opening click itself
    // doesn't immediately close it.
    const id = setTimeout(() => document.addEventListener('mousedown', handler), 0);
    return () => {
      clearTimeout(id);
      document.removeEventListener('mousedown', handler);
    };
  }, [open]);

  return (
    <div className="notif-center" ref={ref}>
      <button
        className="notif-bell"
        onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }}
        aria-label="Notifications"
        aria-expanded={open}
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span className="notif-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>
        )}
        <span
          className={`notif-status-dot ${connected ? 'online' : 'offline'}`}
          title={connected ? 'Live updates connected' : 'Reconnecting…'}
        />
      </button>

      {open && (
        <div className="notif-dropdown">
          <div className="notif-header">
            <span>Notifications</span>
            {unreadCount > 0 && (
              <button className="notif-markall" onClick={markAllRead}>
                <Check size={14} /> Mark all read
              </button>
            )}
          </div>

          <div className="notif-list">
            {notifications.length === 0 ? (
              <div className="notif-empty">
                <Bell size={28} />
                <p>No notifications yet</p>
              </div>
            ) : (
              notifications.map((n) => {
                const Icon = severityIcon(n.severity);
                return (
                  <div
                    key={n.id}
                    className={`notif-item ${n.is_read ? '' : 'unread'} sev-${n.severity || 'none'}`}
                    onClick={() => !n.is_read && markRead([n.id])}
                  >
                    <Icon size={18} className="notif-item-icon" />
                    <div className="notif-item-body">
                      <div className="notif-item-title">{n.title}</div>
                      <div className="notif-item-message">{n.message}</div>
                      <div className="notif-item-time">{timeAgo(n.created_at)}</div>
                    </div>
                    {!n.is_read && <span className="notif-unread-dot" />}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};

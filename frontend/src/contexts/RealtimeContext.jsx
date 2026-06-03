import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
  useMemo,
} from 'react';
import api from '../lib/api';
import { useAuth } from './AuthContext';
import { useToast } from './ToastContext';

/**
 * RealtimeContext
 * ----------------
 * Opens a single Server-Sent Events connection (`/api/stream`) for the whole
 * app and fans events out to subscribers. Centralising it here avoids opening
 * one EventSource per component (browsers cap concurrent connections).
 *
 * Responsibilities:
 *   • maintain the notification list + unread count (seeded via REST, then kept
 *     live over SSE)
 *   • surface a toast for each incoming fraud notification
 *   • let any component subscribe to `transactions_updated` events so dashboards
 *     and tables can refresh themselves without a page reload
 *   • fall back to polling if SSE fails to connect
 */
const RealtimeContext = createContext(null);

export const useRealtime = () => {
  const ctx = useContext(RealtimeContext);
  if (!ctx) throw new Error('useRealtime must be used within a RealtimeProvider');
  return ctx;
};

export const RealtimeProvider = ({ children }) => {
  const { token, isAuthenticated } = useAuth();
  const toast = useToast();

  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [connected, setConnected] = useState(false);

  const esRef = useRef(null);
  const pollRef = useRef(null);
  // Set of listener callbacks for the `transactions_updated` event.
  const txListeners = useRef(new Set());
  // Hold the latest toast helper in a ref so the SSE effect doesn't depend on
  // it. The toast object's identity changes on every toast; if the effect
  // depended on it, the SSE connection would be torn down and reopened
  // constantly, hammering the backend and freezing the UI.
  const toastRef = useRef(toast);
  useEffect(() => {
    toastRef.current = toast;
  }, [toast]);

  const onTransactionsUpdated = useCallback((cb) => {
    txListeners.current.add(cb);
    return () => txListeners.current.delete(cb);
  }, []);

  const fetchNotifications = useCallback(async () => {
    try {
      const res = await api.get('/api/notifications', { params: { limit: 50 } });
      setNotifications(res.data.items || []);
      setUnreadCount(res.data.unread_count || 0);
    } catch {
      // silent — non-critical
    }
  }, []);

  const markRead = useCallback(async (ids) => {
    try {
      await api.post('/api/notifications/mark-read', { notification_ids: ids || null });
      setNotifications((prev) =>
        prev.map((n) => (!ids || ids.includes(n.id) ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => {
        if (!ids) return 0;
        return Math.max(0, prev - ids.length);
      });
    } catch {
      /* ignore */
    }
  }, []);

  const markAllRead = useCallback(() => markRead(null), [markRead]);

  // ── Open / close the SSE connection with the auth lifecycle ──
  useEffect(() => {
    if (!isAuthenticated || !token) return undefined;

    fetchNotifications();

    let cancelled = false;

    const startPolling = () => {
      if (pollRef.current) return;
      pollRef.current = setInterval(() => {
        fetchNotifications();
        txListeners.current.forEach((cb) => cb({ reason: 'poll' }));
      }, 15000);
    };
    const stopPolling = () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };

    let es;
    try {
      es = new EventSource(`/api/stream?token=${encodeURIComponent(token)}`);
      esRef.current = es;

      es.addEventListener('connected', () => {
        if (cancelled) return;
        setConnected(true);
        stopPolling();
      });

      es.addEventListener('notification', (e) => {
        if (cancelled) return;
        try {
          const n = JSON.parse(e.data);
          setNotifications((prev) => [n, ...prev].slice(0, 100));
          setUnreadCount((prev) => prev + 1);
          const kind =
            n.severity === 'critical' || n.severity === 'high' ? 'error' : 'warning';
          toastRef.current.show(n.title ? `${n.title}: ${n.message}` : n.message, kind, 6000);
        } catch {
          /* ignore malformed */
        }
      });

      es.addEventListener('transactions_updated', (e) => {
        if (cancelled) return;
        let data = {};
        try {
          data = JSON.parse(e.data);
        } catch {
          /* ignore */
        }
        txListeners.current.forEach((cb) => cb(data));
      });

      es.onerror = () => {
        setConnected(false);
        // EventSource auto-reconnects; meanwhile poll so the UI stays fresh.
        startPolling();
      };
    } catch {
      startPolling();
    }

    return () => {
      cancelled = true;
      stopPolling();
      if (es) es.close();
      esRef.current = null;
      setConnected(false);
    };
    // Note: `toast` is intentionally NOT a dependency — it's read via toastRef
    // so a new toast never tears down and reopens the SSE connection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, token, fetchNotifications]);

  const value = useMemo(
    () => ({
      notifications,
      unreadCount,
      connected,
      markRead,
      markAllRead,
      refresh: fetchNotifications,
      onTransactionsUpdated,
    }),
    [notifications, unreadCount, connected, markRead, markAllRead, fetchNotifications, onTransactionsUpdated]
  );

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
};

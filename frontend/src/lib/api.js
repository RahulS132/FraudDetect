import axios from 'axios';

/**
 * Shared axios instance.
 *
 * Uses relative `/api/...` URLs so the Vite dev proxy (and the production
 * reverse proxy) routes them to the FastAPI backend. A request interceptor
 * attaches the JWT from localStorage on every call, so individual pages don't
 * have to manage the Authorization header themselves.
 */
const api = axios.create({
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Normalise error messages so callers can surface a clean string.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail;
    error.cleanMessage =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
        ? detail.map((d) => d.msg || JSON.stringify(d)).join(', ')
        : error.message || 'Request failed';
    return Promise.reject(error);
  }
);

export default api;

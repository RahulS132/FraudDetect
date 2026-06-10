import React, { useState, useEffect, useRef } from 'react';
import { Shield, AlertCircle, MailCheck, RefreshCw } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import '../pages/Auth.css';

/**
 * Reusable 6-digit OTP entry used for email verification and login 2FA.
 * On success it logs the user in (via AuthContext.verifyOtp) and calls onDone().
 */
export const OtpForm = ({ email, purpose, initialDevCode, onDone, onBack }) => {
  const { verifyOtp, resendOtp } = useAuth();
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [devCode, setDevCode] = useState(initialDevCode || null);
  const [cooldown, setCooldown] = useState(0);
  const inputRef = useRef(null);

  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (code.trim().length < 6) { setError('Enter the 6-digit code'); return; }
    setLoading(true);
    const res = await verifyOtp(email, code.trim(), purpose);
    setLoading(false);
    if (res.success) onDone();
    else setError(res.error);
  };

  const resend = async () => {
    setError('');
    const res = await resendOtp(email, purpose);
    if (res.success) {
      setDevCode(res.devCode || null);
      setCooldown(60);
    } else {
      setError(res.error);
    }
  };

  const title = purpose === 'login_2fa' ? 'Two-Factor Verification' : 'Verify Your Email';
  const subtitle = purpose === 'login_2fa'
    ? 'Enter the code we sent to finish signing in'
    : 'Enter the code we sent to confirm your email';

  return (
    <div className="auth-container">
      <div className="auth-card">
        <div className="auth-header">
          {purpose === 'login_2fa' ? <Shield size={48} className="auth-logo" /> : <MailCheck size={48} className="auth-logo" />}
          <h1 className="auth-title">{title}</h1>
          <p className="auth-subtitle">{subtitle}<br /><strong>{email}</strong></p>
        </div>

        {devCode && (
          <div className="auth-error" style={{ background: '#eff6ff', color: '#1d4ed8', borderColor: '#bfdbfe' }}>
            <AlertCircle size={18} />
            <span>Dev mode (no SMTP configured): your code is <strong>{devCode}</strong></span>
          </div>
        )}
        {error && (
          <div className="auth-error">
            <AlertCircle size={20} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={submit} className="auth-form">
          <div className="form-group">
            <label className="form-label"><Shield size={18} /> Verification code</label>
            <input
              ref={inputRef}
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              className="form-input"
              style={{ letterSpacing: '0.5em', fontSize: '1.3rem', textAlign: 'center' }}
              placeholder="000000"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
            />
          </div>
          <button type="submit" className="auth-button" disabled={loading}>
            {loading ? 'Verifying…' : 'Verify'}
          </button>
        </form>

        <div className="auth-footer" style={{ display: 'flex', justifyContent: 'space-between' }}>
          <button
            type="button" className="auth-link" style={{ background: 'none' }}
            onClick={resend} disabled={cooldown > 0}
          >
            <RefreshCw size={13} style={{ verticalAlign: -2, marginRight: 4 }} />
            {cooldown > 0 ? `Resend in ${cooldown}s` : 'Resend code'}
          </button>
          {onBack && (
            <button type="button" className="auth-link" style={{ background: 'none' }} onClick={onBack}>
              Back
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default OtpForm;

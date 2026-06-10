import React, { createContext, useState, useContext, useEffect } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Load user from localStorage on mount
    const storedToken = localStorage.getItem('token');
    const storedUser = localStorage.getItem('user');
    
    if (storedToken && storedUser) {
      setToken(storedToken);
      setUser(JSON.parse(storedUser));
      axios.defaults.headers.common['Authorization'] = `Bearer ${storedToken}`;
    }
    
    setLoading(false);
  }, []);

  // Persist a successful auth (token + user) and set the default header.
  const applyAuth = (data) => {
    const { access_token, user: userData } = data;
    setToken(access_token);
    setUser(userData);
    localStorage.setItem('token', access_token);
    localStorage.setItem('user', JSON.stringify(userData));
    axios.defaults.headers.common['Authorization'] = `Bearer ${access_token}`;
  };

  const login = async (email, password) => {
    try {
      const response = await axios.post('/api/auth/login', { email, password });
      if (response.data.access_token) {
        applyAuth(response.data);
        return { success: true, authed: true };
      }
      // Challenge: requires_2fa or requires_verification.
      return { success: true, authed: false, challenge: response.data };
    } catch (error) {
      return { success: false, error: error.response?.data?.detail || 'Login failed' };
    }
  };

  const register = async (email, username, password, fullName) => {
    try {
      const response = await axios.post('/api/auth/register', {
        email, username, password, full_name: fullName, role: 'user',
      });
      // New flow always returns a verification challenge.
      return { success: true, authed: false, challenge: response.data };
    } catch (error) {
      return { success: false, error: error.response?.data?.detail || 'Registration failed' };
    }
  };

  // Verify an OTP (email verification or login 2FA). On success, logs in.
  const verifyOtp = async (email, code, purpose) => {
    const url = purpose === 'login_2fa' ? '/api/auth/verify-2fa' : '/api/auth/verify-email';
    try {
      const response = await axios.post(url, { email, code });
      applyAuth(response.data);
      return { success: true };
    } catch (error) {
      return { success: false, error: error.response?.data?.detail || 'Verification failed' };
    }
  };

  const resendOtp = async (email, purpose) => {
    try {
      const response = await axios.post('/api/auth/resend-otp', { email, purpose });
      return { success: true, devCode: response.data?.dev_code };
    } catch (error) {
      return { success: false, error: error.response?.data?.detail || 'Could not resend code' };
    }
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    delete axios.defaults.headers.common['Authorization'];
  };

  const isAdmin = () => {
    return user?.role === 'admin';
  };

  const value = {
    user,
    token,
    loading,
    login,
    register,
    verifyOtp,
    resendOtp,
    logout,
    isAdmin,
    isAuthenticated: !!token
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

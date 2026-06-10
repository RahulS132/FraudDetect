import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { Chart as ChartJS } from 'chart.js';

const ThemeContext = createContext(null);

export const useTheme = () => {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider');
  return ctx;
};

const applyChartTheme = (theme) => {
  // Keep Chart.js axis/legend text legible in both themes.
  const dark = theme === 'dark';
  ChartJS.defaults.color = dark ? '#cbd5e1' : '#475569';
  ChartJS.defaults.borderColor = dark ? 'rgba(148,163,184,0.18)' : 'rgba(0,0,0,0.08)';
};

export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState(() => {
    const stored = localStorage.getItem('theme');
    if (stored === 'light' || stored === 'dark') return stored;
    // Respect OS preference on first run.
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    applyChartTheme(theme);
  }, [theme]);

  const toggle = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), []);

  return (
    <ThemeContext.Provider value={{ theme, toggle, isDark: theme === 'dark' }}>
      {children}
    </ThemeContext.Provider>
  );
};

export default ThemeProvider;

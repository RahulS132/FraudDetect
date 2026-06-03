import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Upload, Shield, LogOut, User, Receipt, PlusSquare, Users,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import './Sidebar.css';

export const Sidebar = () => {
  const { user, logout, isAdmin } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <Shield size={32} className="sidebar-logo" />
        <h1 className="sidebar-title">FraudDetect</h1>
      </div>

      <div className="sidebar-user">
        <User size={20} />
        <div className="sidebar-user-info">
          <div className="sidebar-username">{user?.username}</div>
          <div className="sidebar-role">{user?.role}</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        <NavLink to="/dashboard" className="sidebar-link">
          <LayoutDashboard size={20} />
          <span>Dashboard</span>
        </NavLink>

        <NavLink to="/transactions" className="sidebar-link">
          <Receipt size={20} />
          <span>Transactions</span>
        </NavLink>

        <NavLink to="/upload" className="sidebar-link">
          <Upload size={20} />
          <span>Upload CSV</span>
        </NavLink>

        {isAdmin() && (
          <>
            <div className="sidebar-section-label">Admin</div>

            <NavLink to="/admin" className="sidebar-link">
              <Shield size={20} />
              <span>Analytics</span>
            </NavLink>

            <NavLink to="/admin/users" className="sidebar-link">
              <Users size={20} />
              <span>User Management</span>
            </NavLink>

            <NavLink to="/admin/transactions" className="sidebar-link">
              <PlusSquare size={20} />
              <span>Manage Transactions</span>
            </NavLink>
          </>
        )}
      </nav>

      <button className="sidebar-logout" onClick={handleLogout}>
        <LogOut size={20} />
        <span>Logout</span>
      </button>
    </div>
  );
};

import React, { useState } from 'react';
import api from '../lib/api';
import { Upload, FileText, CheckCircle, AlertCircle, Loader } from 'lucide-react';
import { Sidebar } from '../components/Sidebar';
import { useNavigate } from 'react-router-dom';
import './UploadCSV.css';

export const UploadCSV = () => {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');
  const [stats, setStats] = useState(null);
  const navigate = useNavigate();

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      if (!selectedFile.name.endsWith('.csv')) {
        setError('Please select a CSV file');
        setFile(null);
        return;
      }
      setFile(selectedFile);
      setError('');
      setSuccess(false);
      setStats(null);
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    
    if (!file) {
      setError('Please select a file');
      return;
    }

    setUploading(true);
    setError('');
    setSuccess(false);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await api.post('/api/transactions/upload-csv', formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      setSuccess(true);
      setStats(response.data.statistics);
      setFile(null);
      
      // Reset file input
      document.getElementById('file-input').value = '';
      
      setTimeout(() => {
        navigate('/dashboard');
      }, 3000);
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to upload file');
    } finally {
      setUploading(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    const droppedFile = e.dataTransfer.files[0];
    if (droppedFile) {
      if (!droppedFile.name.endsWith('.csv')) {
        setError('Please select a CSV file');
        return;
      }
      setFile(droppedFile);
      setError('');
      setSuccess(false);
      setStats(null);
    }
  };

  return (
    <div className="layout">
      <Sidebar />
      <div className="main-content">
        <div className="page-header">
          <h1 className="page-title">Upload CSV</h1>
          <p className="page-subtitle">Upload your transaction data for fraud detection analysis</p>
        </div>

        <div className="upload-container">
          <form onSubmit={handleUpload} className="upload-form">
            <div
              className={`upload-dropzone ${file ? 'has-file' : ''}`}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
            >
              <input
                type="file"
                id="file-input"
                accept=".csv"
                onChange={handleFileChange}
                className="file-input"
              />
              <label htmlFor="file-input" className="file-label">
                {file ? (
                  <>
                    <FileText size={48} className="upload-icon" />
                    <div className="file-name">{file.name}</div>
                    <div className="file-size">
                      {(file.size / 1024).toFixed(2)} KB
                    </div>
                    <div className="upload-hint">Click or drag to change file</div>
                  </>
                ) : (
                  <>
                    <Upload size={48} className="upload-icon" />
                    <div className="upload-text">
                      Drag and drop your CSV file here
                    </div>
                    <div className="upload-hint">or click to browse</div>
                  </>
                )}
              </label>
            </div>

            {error && (
              <div className="message message-error">
                <AlertCircle size={20} />
                <span>{error}</span>
              </div>
            )}

            {success && (
              <div className="message message-success">
                <CheckCircle size={20} />
                <span>File uploaded and processed successfully!</span>
              </div>
            )}

            {stats && (
              <div className="upload-stats">
                <h3 className="stats-title">Processing Results</h3>
                <div className="stats-grid-small">
                  <div className="stat-item">
                    <span className="stat-item-label">Total Transactions</span>
                    <span className="stat-item-value">{stats.total_transactions}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-item-label">Approved</span>
                    <span className="stat-item-value stat-success">{stats.approved_transactions}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-item-label">Rejected</span>
                    <span className="stat-item-value stat-warning">{stats.rejected_transactions}</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-item-label">Fraud Detected</span>
                    <span className="stat-item-value stat-danger">{stats.fraud_detected}</span>
                  </div>
                </div>
                <p className="redirect-message">Redirecting to dashboard...</p>
              </div>
            )}

            <button
              type="submit"
              className="upload-button"
              disabled={!file || uploading}
            >
              {uploading ? (
                <>
                  <Loader size={20} className="spinner" />
                  Processing...
                </>
              ) : (
                <>
                  <Upload size={20} />
                  Upload and Process
                </>
              )}
            </button>
          </form>

          <div className="upload-info">
            <h3 className="info-title">CSV Format Requirements</h3>
            <ul className="info-list">
              <li>File must be in CSV format</li>
              <li>Must contain columns: Time, V1-V28, Amount, Class</li>
              <li>Class column: 0 = Legitimate, 1 = Fraud</li>
              <li>Compatible with Kaggle Credit Card Fraud Detection dataset</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

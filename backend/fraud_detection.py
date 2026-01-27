import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from typing import List, Tuple
import io

class FraudDetector:
    def __init__(self, contamination=0.1, random_state=42):
        """
        Initialize the fraud detector with Isolation Forest
        
        Args:
            contamination: Expected proportion of outliers (fraud) in the dataset
            random_state: Random seed for reproducibility
        """
        self.contamination = contamination
        self.random_state = random_state
        self.model = IsolationForest(
            contamination=contamination,
            random_state=random_state,
            n_estimators=100,
            max_samples='auto',
            bootstrap=False,
            n_jobs=-1
        )
        self.scaler = StandardScaler()
        self.feature_columns = None
    
    def process_csv(self, csv_content: bytes) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Process uploaded CSV file and detect fraud
        
        Args:
            csv_content: CSV file content as bytes
            
        Returns:
            Tuple of (original_df, results_df)
        """
        # Read CSV
        df = pd.read_csv(io.BytesIO(csv_content))
        
        # Validate required columns
        required_columns = ['Time'] + [f'V{i}' for i in range(1, 29)] + ['Amount', 'Class']
        missing_columns = set(required_columns) - set(df.columns)
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        
        # Store feature columns (exclude Class)
        self.feature_columns = [col for col in df.columns if col != 'Class']
        
        # Prepare features for anomaly detection
        X = df[self.feature_columns].copy()
        
        # Scale features
        X_scaled = self.scaler.fit_transform(X)
        
        # Fit and predict with Isolation Forest
        self.model.fit(X_scaled)
        anomaly_predictions = self.model.predict(X_scaled)
        anomaly_scores = self.model.score_samples(X_scaled)
        
        # Create results dataframe
        results_df = df.copy()
        
        # Anomaly prediction: -1 = outlier (fraud), 1 = inlier (normal)
        results_df['is_anomaly'] = anomaly_predictions == -1
        results_df['anomaly_score'] = anomaly_scores
        
        # Determine fraud: either marked as fraud in data (Class=1) OR detected as anomaly
        results_df['is_fraud'] = (results_df['Class'] == 1) | results_df['is_anomaly']
        
        # Determine approval: approved if NOT fraud
        results_df['is_approved'] = ~results_df['is_fraud']
        
        return df, results_df
    
    def get_statistics(self, results_df: pd.DataFrame) -> dict:
        """
        Calculate statistics from detection results
        
        Args:
            results_df: DataFrame with detection results
            
        Returns:
            Dictionary with statistics
        """
        total = len(results_df)
        fraud_detected = results_df['is_fraud'].sum()
        approved = results_df['is_approved'].sum()
        rejected = total - approved
        legitimate = total - fraud_detected
        
        return {
            'total_transactions': int(total),
            'approved_transactions': int(approved),
            'rejected_transactions': int(rejected),
            'fraud_detected': int(fraud_detected),
            'legitimate_transactions': int(legitimate),
            'fraud_percentage': float(fraud_detected / total * 100) if total > 0 else 0.0,
            'approval_rate': float(approved / total * 100) if total > 0 else 0.0
        }

# Global detector instance
detector = FraudDetector()

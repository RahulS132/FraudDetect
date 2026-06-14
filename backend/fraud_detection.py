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
        
        # Store feature columns: only the numeric Kaggle features the model was
        # designed for. We deliberately exclude Class AND any extra business
        # columns (merchant, category, tag, description, etc.) that a CSV may
        # carry — those are metadata, not model inputs, and would break the
        # scaler if fed in.
        self.feature_columns = ['Time'] + [f'V{i}' for i in range(1, 29)] + ['Amount']

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


# ──────────────────────────────────────────────────────────────────────────────
# Rule-based fraud scoring for manually-entered transactions
# ──────────────────────────────────────────────────────────────────────────────
# Manually created transactions (admin or user) have no V1–V28 PCA features, so
# the Isolation Forest cannot score them. Instead we run a transparent, fully
# backend-side heuristic engine that returns a 0–100 fraud score, a severity
# band, and the contributing reasons. This keeps fraud detection on the server
# and gives meaningful, explainable results for hand-entered data.

class RuleBasedFraudScorer:
    """Deterministic, explainable risk scorer for manual transactions."""

    # Fraud-risk threshold: at/above this score a transaction is flagged.
    FRAUD_THRESHOLD = 50.0

    # Per-category baseline risk weight (0–25 points).
    CATEGORY_RISK = {
        "Transfer": 25,
        "Investment": 20,
        "Travel": 18,
        "Entertainment": 14,
        "Shopping": 12,
        "Other": 12,
        "Healthcare": 8,
        "Utilities": 6,
        "Food": 5,
        "Insurance": 5,
        "Rent": 4,
        "Salary": 3,
    }

    # Amount bands → points (0–40). High value == higher risk.
    AMOUNT_BANDS = [
        (10_000, 40),
        (5_000, 32),
        (2_500, 24),
        (1_000, 16),
        (500, 10),
        (100, 5),
        (0, 0),
    ]

    def score(self, amount: float, category: str = "Other",
              txn_time=None, recent_count: int = 0,
              user_mean: float = None, user_std: float = None) -> dict:
        """
        Compute a fraud assessment for a single manual transaction.

        Combines absolute-amount risk, a **per-account statistical anomaly**
        (how far this amount sits from the account's own spending pattern, in
        standard deviations), category, time-of-day, and velocity. The per-
        account z-score is the core "algorithm" — a transaction that is wildly
        out of line with a user's history is flagged even if its absolute amount
        is modest, and a large-but-normal amount for a high-spend account isn't
        over-penalised.

        Args:
            amount: transaction amount in dollars
            category: business category
            txn_time: datetime of the transaction (time-of-day risk)
            recent_count: transactions the user made in the recent window (velocity)
            user_mean / user_std: the account's historical amount mean / std dev

        Returns a dict with: fraud_score, is_fraud, is_approved, severity,
        anomaly_score (for chart compatibility), z_score and reasons.
        """
        reasons = []
        score = 0.0
        z = None

        # 1) Absolute amount risk
        amount_points = 0
        for threshold, pts in self.AMOUNT_BANDS:
            if amount >= threshold:
                amount_points = pts
                break
        if amount_points:
            reasons.append(f"High amount (${amount:,.2f}) → +{amount_points}")
        score += amount_points

        # 2) Per-account statistical anomaly (z-score) — the core algorithm
        if user_mean is not None and user_std is not None and user_std > 0:
            z = (amount - user_mean) / user_std
            if z > 1.0:
                z_points = min(40.0, (z - 1.0) * 18.0)
                score += z_points
                reasons.append(f"Amount is {z:.1f}σ above this account's average → +{z_points:.0f}")
        elif user_mean is not None and user_mean > 0 and amount > user_mean * 4:
            # Too little history for a std dev, but the amount dwarfs the average.
            score += 22
            reasons.append("Amount far above this account's typical spend → +22")

        # 3) Category risk
        cat_points = self.CATEGORY_RISK.get(category, self.CATEGORY_RISK["Other"])
        score += cat_points
        if cat_points >= 18:
            reasons.append(f"High-risk category '{category}' → +{cat_points}")

        # 4) Time-of-day risk (transactions 00:00–05:00 are riskier)
        if txn_time is not None:
            try:
                hour = txn_time.hour
                if 0 <= hour < 5:
                    score += 15
                    reasons.append(f"Unusual hour ({hour:02d}:00) → +15")
                elif 5 <= hour < 7 or 22 <= hour <= 23:
                    score += 6
                    reasons.append(f"Off-hours ({hour:02d}:00) → +6")
            except Exception:
                pass

        # 5) Velocity risk (many transactions in a short window)
        if recent_count >= 8:
            score += 20
            reasons.append(f"High velocity ({recent_count} recent) → +20")
        elif recent_count >= 4:
            score += 12
            reasons.append(f"Elevated velocity ({recent_count} recent) → +12")
        elif recent_count >= 2:
            score += 6
            reasons.append(f"Multiple recent transactions ({recent_count}) → +6")

        score = float(max(0.0, min(100.0, score)))
        severity = self.severity_for(score)
        is_fraud = score >= self.FRAUD_THRESHOLD

        # Map to an anomaly_score on the same sign convention used by the
        # Isolation Forest path (lower = more anomalous), so existing charts
        # that read anomaly_score keep working for manual transactions.
        anomaly_score = float(round(0.5 - (score / 100.0), 6))

        if not reasons:
            reasons.append("No significant risk signals")

        return {
            "fraud_score": round(score, 2),
            "is_fraud": bool(is_fraud),
            "is_approved": bool(not is_fraud),
            "severity": severity,
            "anomaly_score": anomaly_score,
            "z_score": round(z, 2) if z is not None else None,
            "reasons": reasons,
        }

    @staticmethod
    def severity_for(score: float) -> str:
        """Bucket a 0–100 fraud score into a severity band."""
        if score >= 85:
            return "critical"
        if score >= 70:
            return "high"
        if score >= 45:
            return "medium"
        if score >= 20:
            return "low"
        return "none"


rule_scorer = RuleBasedFraudScorer()


# ──────────────────────────────────────────────────────────────────────────────
# Module-level compatibility API
# ──────────────────────────────────────────────────────────────────────────────
# The admin transaction routes and the search service import these two function
# names. They are thin adapters over RuleBasedFraudScorer so callers get a stable
# functional API regardless of the scorer's internal shape.

def severity_from_score(anomaly_score, is_fraud: bool) -> str:
    """Map an anomaly_score (lower = more anomalous) onto a severity band.

    Used by the search service to derive a severity for detection_result rows
    that predate the stored `severity` field. Non-fraud rows are 'none'.
    """
    if not is_fraud:
        return "none"
    if anomaly_score is None:
        return "medium"
    # Convert anomaly_score (≈ -0.8..0.2, lower = riskier) to the 0–100 scale the
    # rule scorer's bands use, then reuse its bucketing for consistency.
    score = max(0.0, min(100.0, (0.5 - float(anomaly_score)) * 100.0))
    return RuleBasedFraudScorer.severity_for(score)


def score_manual_transaction(
    amount: float,
    is_fraud_override=None,
    category: str = "Other",
    transaction_time=None,
    recent_count: int = 0,
    user_mean: float = None,
    user_std: float = None,
) -> dict:
    """Score a single hand-entered transaction.

    Delegates to the rule-based scorer (which combines absolute amount, a
    per-account statistical anomaly, category, time and velocity), then applies
    an optional admin override that forces the fraud flag. Returns a dict with:
        is_fraud, is_approved, anomaly_score, severity, fraud_score, reasons.
    """
    result = rule_scorer.score(
        amount=amount,
        category=category or "Other",
        txn_time=transaction_time,
        recent_count=recent_count,
        user_mean=user_mean,
        user_std=user_std,
    )

    if is_fraud_override is not None:
        forced = bool(is_fraud_override)
        result["is_fraud"] = forced
        result["is_approved"] = not forced
        if forced:
            # Ensure score/severity/anomaly reflect a real flag even if the
            # heuristic rated it benign.
            result["fraud_score"] = max(result.get("fraud_score", 0.0), 75.0)
            result["severity"] = RuleBasedFraudScorer.severity_for(result["fraud_score"])
            result["anomaly_score"] = float(round(0.5 - (result["fraud_score"] / 100.0), 6))
        else:
            result["severity"] = "none"

    return result

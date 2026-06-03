from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Any, Dict
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"

class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str
    role: UserRole = UserRole.USER

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('Password must be at least 6 characters long')
        return v

    @validator('username')
    def validate_username(cls, v):
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters long')
        if not v.isalnum():
            raise ValueError('Username must contain only alphanumeric characters')
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserInDB(UserBase):
    id: str
    role: UserRole
    created_at: datetime

    class Config:
        from_attributes = True

class UserResponse(UserBase):
    id: str
    role: UserRole
    created_at: datetime

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class TokenData(BaseModel):
    id: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None

class TransactionData(BaseModel):
    Time: float
    V1: float
    V2: float
    V3: float
    V4: float
    V5: float
    V6: float
    V7: float
    V8: float
    V9: float
    V10: float
    V11: float
    V12: float
    V13: float
    V14: float
    V15: float
    V16: float
    V17: float
    V18: float
    V19: float
    V20: float
    V21: float
    V22: float
    V23: float
    V24: float
    V25: float
    V26: float
    V27: float
    V28: float
    Amount: float
    Class: int

class DetectionResult(BaseModel):
    transaction_id: str
    user_id: str
    is_fraud: bool
    is_approved: bool
    anomaly_score: float
    actual_class: int
    created_at: datetime

class DashboardStats(BaseModel):
    total_transactions: int
    approved_transactions: int
    rejected_transactions: int
    fraud_detected: int
    legitimate_transactions: int
    fraud_percentage: float
    approval_rate: float

class AdminStats(BaseModel):
    total_users: int
    total_transactions: int
    total_fraud_detected: int
    global_fraud_rate: float
    global_approval_rate: float
    approved_transactions: int
    rejected_transactions: int

class UserFraudRate(BaseModel):
    user_id: str
    username: str
    email: str
    total_transactions: int
    fraud_count: int
    fraud_rate: float


# ════════════════════════════════════════════════════════════════════════════
#  NEW MODELS — feature expansion
#  (tags/labels, manual & bulk admin transactions, notifications, audit log,
#   search, admin per-user views)
# ════════════════════════════════════════════════════════════════════════════

# ── Transaction tags / labels ────────────────────────────────────────────────
class TransactionTag(str, Enum):
    """Canonical labels available for categorising a transaction.

    Stored as plain strings on the transaction document under `tag`. Kept as an
    enum so the API validates input and the frontend can render a fixed picker.
    """
    FOOD = "Food"
    RENT = "Rent"
    SALARY = "Salary"
    UTILITIES = "Utilities"
    ENTERTAINMENT = "Entertainment"
    INVESTMENT = "Investment"
    TRAVEL = "Travel"
    INSURANCE = "Insurance"
    OTHER = "Other"


class CreationSource(str, Enum):
    """How a transaction entered the system. Existing CSV rows are back-filled
    logically as `csv_upload` (absence of the field is treated as csv_upload)."""
    CSV_UPLOAD = "csv_upload"
    ADMIN_MANUAL = "admin_manual"
    ADMIN_BULK = "admin_bulk"


class FraudSeverity(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Manual / bulk transaction creation (admin) ───────────────────────────────
class ManualTransactionCreate(BaseModel):
    """A single admin-entered transaction.

    The Kaggle PCA features (V1–V28) are optional here — an admin entering a
    real-world transaction supplies business fields instead. When V-features are
    absent the fraud score is computed by a lightweight rule-based heuristic
    (see fraud_detection.score_manual_transaction)."""
    amount: float = Field(..., ge=0, description="Transaction amount in dollars")
    category: Optional[str] = Field(None, max_length=100)
    tag: Optional[TransactionTag] = None
    description: Optional[str] = Field(None, max_length=1000)
    transaction_time: Optional[datetime] = Field(
        None, description="Business date/time of the transaction (defaults to now)"
    )
    is_fraud_override: Optional[bool] = Field(
        None, description="If set, forces the fraud flag instead of using the heuristic"
    )

    @validator("amount")
    def validate_amount(cls, v):
        if v < 0:
            raise ValueError("Amount cannot be negative")
        if v > 1_000_000_000:
            raise ValueError("Amount is unrealistically large")
        return float(v)


class BulkTransactionCreate(BaseModel):
    """Batch of manual transactions to create for one target user."""
    user_id: str = Field(..., description="Target user the transactions belong to")
    transactions: List[ManualTransactionCreate] = Field(..., min_items=1, max_items=1000)

    @validator("transactions")
    def non_empty(cls, v):
        if not v:
            raise ValueError("At least one transaction is required")
        return v


class BulkCreateResult(BaseModel):
    success: bool
    created_count: int
    failed_count: int
    fraud_flagged: int
    errors: List[Dict[str, Any]] = []
    transaction_ids: List[str] = []


# ── Tag update on an existing transaction ────────────────────────────────────
class TagUpdate(BaseModel):
    merchant: Optional[str] = Field(None, max_length=200)   # business name
    tag: Optional[TransactionTag] = None                    # canonical category
    category: Optional[str] = Field(None, max_length=100)   # legacy free-text (still accepted)
    description: Optional[str] = Field(None, max_length=1000)


# ── Unified transaction detail (joins transaction + detection_result) ────────
class TransactionDetail(BaseModel):
    transaction_id: str
    user_id: str
    username: Optional[str] = None
    user_email: Optional[str] = None
    amount: float
    transaction_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    merchant: Optional[str] = None               # business name (e.g. "Woolworths")
    category: Optional[str] = None               # free-text category (legacy)
    tag: Optional[str] = None                    # canonical label, shown as "Category" in UI
    description: Optional[str] = None
    fraud_score: Optional[float] = None          # anomaly_score
    fraud_severity: Optional[str] = None
    is_fraud: Optional[bool] = None
    is_approved: Optional[bool] = None
    fraud_status: Optional[str] = None           # "Fraud" | "Approved"
    creation_source: Optional[str] = None
    actual_class: Optional[int] = None
    metadata: Dict[str, Any] = {}


class TransactionListResponse(BaseModel):
    items: List[TransactionDetail]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Notifications ────────────────────────────────────────────────────────────
class NotificationType(str, Enum):
    FRAUD_ALERT = "fraud_alert"
    SYSTEM = "system"
    BULK_IMPORT = "bulk_import"


class NotificationResponse(BaseModel):
    id: str
    user_id: Optional[str] = None    # recipient; None => broadcast to all admins
    type: str
    title: str
    message: str
    severity: str
    is_read: bool
    transaction_id: Optional[str] = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    unread_count: int


class MarkReadRequest(BaseModel):
    notification_ids: Optional[List[str]] = None   # None => mark all read


# ── Admin per-user views ─────────────────────────────────────────────────────
class AdminUserSummary(BaseModel):
    user_id: str
    username: str
    email: str
    full_name: Optional[str] = None
    role: str
    created_at: datetime
    total_transactions: int = 0
    fraud_count: int = 0
    fraud_rate: float = 0.0


class UserAnalytics(BaseModel):
    user_id: str
    username: str
    email: str
    full_name: Optional[str] = None
    total_transactions: int
    approved_transactions: int
    rejected_transactions: int
    fraud_detected: int
    legitimate_transactions: int
    fraud_percentage: float
    approval_rate: float
    total_volume: float
    avg_transaction: float
    risk_score: float                 # 0–100 composite
    risk_level: str                   # low / medium / high / critical
    spending_by_tag: List[Dict[str, Any]] = []
    transactions_over_time: Dict[str, Any] = {}

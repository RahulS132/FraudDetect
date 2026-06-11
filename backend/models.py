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
    merchant: Optional[str] = Field(None, max_length=200)
    country: Optional[str] = Field(None, max_length=100)
    card_type: Optional[str] = Field(None, max_length=50)
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
    # account / status (second expansion)
    status: str = "active"
    credit_limit: float = 5000.0
    current_balance: float = 0.0
    available_credit: float = 5000.0
    credit_utilization: float = 0.0
    is_frozen: bool = False


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


# ════════════════════════════════════════════════════════════════════════════
#  SECOND EXPANSION — account/balance, blocking, transaction rules, fraud config
# ════════════════════════════════════════════════════════════════════════════

# ── Account status & balance ─────────────────────────────────────────────────
class AccountStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"
    UNDER_REVIEW = "under_review"


# Default account values applied to users that predate the balance system.
DEFAULT_CREDIT_LIMIT = 5000.0


class AccountSummary(BaseModel):
    """A user's balance / credit snapshot.

    Semantics (credit-card model):
      current_balance  = credit used / amount owed (0 = nothing owed)
      available_credit = credit_limit - current_balance  (0 when credit_suspended)
    """
    user_id: str
    username: Optional[str] = None
    email: Optional[str] = None
    status: str = AccountStatus.ACTIVE.value
    credit_limit: float = DEFAULT_CREDIT_LIMIT
    has_credit_limit: bool = True            # False when credit_limit == 0 (no limit)
    current_balance: float = 0.0             # spendable money the user has
    credit_used: float = 0.0                 # credit line drawn
    available_credit: float = DEFAULT_CREDIT_LIMIT
    spending_power: float = DEFAULT_CREDIT_LIMIT  # balance + available credit
    credit_utilization: float = 0.0          # this month's % of limit (uncapped)
    monthly_spend: float = 0.0               # this calendar month's approved spend
    total_spending: float = 0.0
    total_deposits: float = 0.0
    total_transactions: int = 0
    is_frozen: bool = False
    credit_suspended: bool = False
    currency: str = "USD"
    updated_at: Optional[datetime] = None
    force_2fa: bool = False
    email_verified: bool = True


class AmountRequest(BaseModel):
    amount: float = Field(..., gt=0, le=1_000_000_000)
    note: Optional[str] = Field(None, max_length=500)


class SetBalanceRequest(BaseModel):
    balance: float = Field(..., ge=0, le=1_000_000_000)
    note: Optional[str] = Field(None, max_length=500)


class CreditLimitRequest(BaseModel):
    """Either set an absolute credit_limit, or apply a signed delta."""
    credit_limit: Optional[float] = Field(None, ge=0, le=1_000_000_000)
    delta: Optional[float] = Field(None, ge=-1_000_000_000, le=1_000_000_000)
    note: Optional[str] = Field(None, max_length=500)

    @validator("delta")
    def one_of(cls, v, values):
        if v is None and values.get("credit_limit") is None:
            raise ValueError("Provide either credit_limit or delta")
        return v


class ToggleRequest(BaseModel):
    enabled: bool
    note: Optional[str] = Field(None, max_length=500)


class AccountEvent(BaseModel):
    id: str
    user_id: str
    type: str
    amount: Optional[float] = None
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    actor_id: Optional[str] = None
    actor_email: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime


class AccountDetailResponse(BaseModel):
    account: AccountSummary
    history: List[AccountEvent] = []


# ── User blocking / status ───────────────────────────────────────────────────
class BlockReasonCode(str, Enum):
    FRAUD = "fraud"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    MANUAL_REVIEW = "manual_review"
    ACCOUNT_VIOLATION = "account_violation"
    CUSTOM = "custom"


class BlockRequest(BaseModel):
    reason_code: BlockReasonCode
    reason: Optional[str] = Field(None, max_length=500)
    notes: Optional[str] = Field(None, max_length=1000)


class UnblockRequest(BaseModel):
    notes: Optional[str] = Field(None, max_length=1000)


class StatusRequest(BaseModel):
    status: AccountStatus
    notes: Optional[str] = Field(None, max_length=1000)


class StatusEvent(BaseModel):
    id: str
    user_id: str
    action: str
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    notes: Optional[str] = None
    actor_id: Optional[str] = None
    actor_email: Optional[str] = None
    created_at: datetime


# ── Transaction blocking rules ───────────────────────────────────────────────
class RuleType(str, Enum):
    MERCHANT = "merchant"
    CATEGORY = "category"
    AMOUNT_RANGE = "amount_range"
    COUNTRY = "country"
    CARD_TYPE = "card_type"
    USER = "user"


class RuleAction(str, Enum):
    BLOCK = "block"
    FLAG = "flag"


class TransactionRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    rule_type: RuleType
    action: RuleAction = RuleAction.BLOCK
    enabled: bool = True
    # Flexible config; validated semantically per rule_type in the rules engine.
    # merchant/category/country/card_type → {"value": "..."} or {"values": [...]}
    # amount_range → {"min": float?, "max": float?}
    # user → {"user_id": "..."}
    config: Dict[str, Any] = {}
    description: Optional[str] = Field(None, max_length=500)


class TransactionRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    rule_type: Optional[RuleType] = None
    action: Optional[RuleAction] = None
    enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None
    description: Optional[str] = Field(None, max_length=500)


class TransactionRuleResponse(BaseModel):
    id: str
    name: str
    rule_type: str
    action: str
    enabled: bool
    config: Dict[str, Any] = {}
    description: Optional[str] = None
    trigger_count: int = 0
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# ── Fraud auto-block config ──────────────────────────────────────────────────
class FraudConfigResponse(BaseModel):
    auto_block_threshold: float = 95.0     # 0–100 fraud score
    auto_flag_threshold: float = 80.0
    flag_account_on_block: bool = True
    notify_admins: bool = True
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None


class FraudConfigUpdate(BaseModel):
    auto_block_threshold: Optional[float] = Field(None, ge=0, le=100)
    auto_flag_threshold: Optional[float] = Field(None, ge=0, le=100)
    flag_account_on_block: Optional[bool] = None
    notify_admins: Optional[bool] = None


class FraudEventResponse(BaseModel):
    id: str
    transaction_id: Optional[str] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    fraud_score: float
    severity: str
    threshold: Optional[float] = None
    action: str                # blocked | flagged
    reason: Optional[str] = None
    created_at: datetime


# ── Audit log (searchable) ───────────────────────────────────────────────────
class AuditLogResponse(BaseModel):
    id: str
    action: str
    actor_id: Optional[str] = None
    actor_email: Optional[str] = None
    target_user_id: Optional[str] = None
    target_username: Optional[str] = None
    details: Dict[str, Any] = {}
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ── Email verification / 2FA (Phase 2) ───────────────────────────────────────
class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=4, max_length=10)


class ResendOtpRequest(BaseModel):
    email: EmailStr
    purpose: str = Field("verify_email", pattern="^(verify_email|login_2fa)$")


class Verify2FARequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=4, max_length=10)


class Toggle2FARequest(BaseModel):
    enabled: bool


class LoginAttemptResponse(BaseModel):
    id: str
    email: Optional[str] = None
    success: bool
    reason: Optional[str] = None
    stage: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime

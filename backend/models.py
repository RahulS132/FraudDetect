from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
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
    email: Optional[str] = None

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

from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from config import get_settings
from database import users_collection
from models import TokenData, UserRole
from bson import ObjectId

settings = get_settings()
# Password hashing
# HTTP Bearer scheme for JWT
security = HTTPBearer()

def _password_to_bcrypt_bytes(password: str) -> bytes:
    """Encode a password for bcrypt and truncate to bcrypt's 72-byte limit.

    Bcrypt only accepts the first 72 bytes of the input. We truncate the UTF-8
    byte sequence directly so hashing and verification use the exact same input.
    """
    return password.encode("utf-8")[:72]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a bcrypt hash."""
    safe_password = _password_to_bcrypt_bytes(plain_password)
    return bcrypt.checkpw(safe_password, hashed_password.encode("utf-8"))


def get_password_hash(password: str) -> str:
    """Hash a password with bcrypt after applying the 72-byte limit."""
    safe_password = _password_to_bcrypt_bytes(password)
    hashed = bcrypt.hashpw(safe_password, bcrypt.gensalt())
    return hashed.decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> TokenData:
    """Verify a JWT token and return token data."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        email: str = payload.get("sub")
        user_id: str = payload.get("id")
        role: str = payload.get("role")
        if email is None or user_id is None:
            # Token is missing required claims — likely an old token issued
            # before id/role were added. Force the client to re-login.
            raise credentials_exception
        return TokenData(id=user_id, email=email, role=role)
    except JWTError:
        raise credentials_exception


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Lightweight current-user dependency built straight from the JWT.

    No DB roundtrip — returns just {id, email, role}. Use this on hot paths
    (dashboards, listings, anything called on every request). If a handler
    needs profile fields like username/full_name/created_at, use
    get_full_current_user instead.
    """
    token_data = verify_token(credentials.credentials)
    return {
        "id": token_data.id,
        "email": token_data.email,
        "role": token_data.role,
    }


async def get_full_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Heavier current-user dependency that fetches the full user document.

    Use only when the handler genuinely needs profile fields beyond id/email/role
    (e.g. the /me endpoint that returns the full UserResponse).
    """
    token_data = verify_token(credentials.credentials)
    user = users_collection.find_one({"email": token_data.email})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user["id"] = str(user["_id"])
    return user


async def get_current_admin(current_user: dict = Depends(get_current_user)):
    """Verify that the current user is an admin (reads role from the JWT)."""
    if current_user.get("role") != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

def authenticate_user(email: str, password: str):
    """Authenticate a user by email and password"""
    user = users_collection.find_one({"email": email})
    if not user:
        return False
    if not verify_password(password, user["hashed_password"]):
        return False
    return user

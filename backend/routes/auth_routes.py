from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime, timedelta
from models import UserCreate, UserLogin, Token, UserResponse, UserRole
from database import users_collection
from auth import (
    get_password_hash,
    authenticate_user,
    create_access_token,
    get_full_current_user,
)
from config import get_settings

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
settings = get_settings()

@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate):
    """Register a new user"""
    # Check if email already exists
    if users_collection.find_one({"email": user.email}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if username already exists
    if users_collection.find_one({"username": user.username}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create user document
    user_doc = {
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "hashed_password": get_password_hash(user.password),
        "role": user.role.value,
        "created_at": datetime.utcnow()
    }
    
    # Insert into database
    result = users_collection.insert_one(user_doc)
    user_doc["id"] = str(result.inserted_id)

    # Create access token — include id+role so request handlers don't have to
    # re-query Mongo on every request just to get them.
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user.email,
            "id": user_doc["id"],
            "role": user_doc["role"],
        },
        expires_delta=access_token_expires,
    )
    
    # Prepare user response (exclude hashed_password)
    user_response = UserResponse(
        id=user_doc["id"],
        email=user_doc["email"],
        username=user_doc["username"],
        full_name=user_doc["full_name"],
        role=UserRole(user_doc["role"]),
        created_at=user_doc["created_at"]
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=user_response
    )

@router.post("/login", response_model=Token)
async def login(credentials: UserLogin):
    """Login and get access token"""
    user = authenticate_user(credentials.email, credentials.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create access token — include id+role so request handlers don't have to
    # re-query Mongo on every request just to get them.
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={
            "sub": user["email"],
            "id": str(user["_id"]),
            "role": user["role"],
        },
        expires_delta=access_token_expires,
    )

    # Prepare user response (exclude hashed_password)
    user_response = UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        username=user["username"],
        full_name=user.get("full_name"),
        role=UserRole(user["role"]),
        created_at=user["created_at"]
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=user_response
    )

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_full_current_user)):
    """Get current user information (fetches full profile from Mongo)."""
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        username=current_user["username"],
        full_name=current_user.get("full_name"),
        role=UserRole(current_user["role"]),
        created_at=current_user["created_at"]
    )

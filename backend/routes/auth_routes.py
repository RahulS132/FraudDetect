"""Authentication routes — registration, email verification, login, 2FA.

Flow summary:
  register        → creates an UNVERIFIED user, emails a 6-digit OTP, returns a
                    {requires_verification} challenge (no token yet).
  verify-email    → checks the OTP, marks the email verified, returns a token.
  login           → password check → blocked check → email-verified check →
                    if 2FA enabled, emails an OTP and returns {requires_2fa};
                    otherwise returns a token. Every attempt is logged.
  verify-2fa      → checks the login OTP, returns a token.
  resend-otp      → re-sends a verification / 2FA code (rate limited).

Backward compatibility: existing users with no ``email_verified`` field are
treated as verified (legacy), so current logins keep working.
"""

from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.concurrency import run_in_threadpool
from datetime import datetime, timedelta

from models import (
    UserCreate, UserLogin, Token, UserResponse, UserRole,
    VerifyEmailRequest, ResendOtpRequest, Verify2FARequest,
)
from database import users_collection
from auth import (
    get_password_hash,
    authenticate_user,
    create_access_token,
    get_full_current_user,
)
from config import get_settings
from services import otp as otp_service
from services import security_log

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
settings = get_settings()


# ── helpers ──────────────────────────────────────────────────────────────────

def _client_info(request: Request):
    ip = request.client.host if request.client else None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",")[0].strip()
    return ip, request.headers.get("user-agent")


def _issue_token(user: dict) -> Token:
    expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"], "id": str(user["_id"]), "role": user["role"]},
        expires_delta=expires,
    )
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=str(user["_id"]),
            email=user["email"],
            username=user["username"],
            full_name=user.get("full_name"),
            role=UserRole(user["role"]),
            created_at=user["created_at"],
        ),
    )


def _is_verified(user: dict) -> bool:
    # Missing field => legacy account, treated as verified.
    return user.get("email_verified", True) is not False


def _twofa_enabled(user: dict) -> bool:
    return bool(user.get("force_2fa", False))


# ── registration ─────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate):
    """Create an unverified account and email a verification code."""
    if await run_in_threadpool(lambda: users_collection.find_one({"email": user.email})):
        raise HTTPException(status_code=400, detail="Email already registered")
    if await run_in_threadpool(lambda: users_collection.find_one({"username": user.username})):
        raise HTTPException(status_code=400, detail="Username already taken")

    now = datetime.utcnow()
    user_doc = {
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "hashed_password": get_password_hash(user.password),
        "role": user.role.value,
        "created_at": now,
        "status": "active",
        "email_verified": False,
        "force_2fa": False,
        "account": {
            "credit_limit": 5000.0,
            "current_balance": 0.0,
            "credit_used": 0.0,
            "total_spending": 0.0,
            "total_deposits": 0.0,
            "total_transactions": 0,
            "is_frozen": False,
            "credit_suspended": False,
            "currency": "USD",
            "updated_at": now,
        },
    }
    await run_in_threadpool(lambda: users_collection.insert_one(user_doc))

    try:
        otp_result = await run_in_threadpool(otp_service.create_and_send, user.email, "verify_email")
    except ValueError as e:
        otp_result = {"sent": False, "dev": False, "error": str(e)}

    return {
        "requires_verification": True,
        "email": user.email,
        "message": "Account created. Enter the verification code sent to your email.",
        "dev_code": otp_result.get("dev_code"),
        "email_sent": otp_result.get("sent", False),
    }


@router.post("/verify-email", response_model=Token)
async def verify_email(body: VerifyEmailRequest):
    """Verify the registration OTP and return an access token."""
    user = await run_in_threadpool(lambda: users_collection.find_one({"email": body.email}))
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    try:
        await run_in_threadpool(otp_service.verify, body.email, body.code, "verify_email")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await run_in_threadpool(
        lambda: users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"email_verified": True, "email_verified_at": datetime.utcnow()}},
        )
    )
    user["email_verified"] = True
    return _issue_token(user)


# ── login ────────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(credentials: UserLogin, request: Request):
    ip, ua = _client_info(request)
    user = await run_in_threadpool(authenticate_user, credentials.email, credentials.password)
    if not user:
        await run_in_threadpool(
            lambda: security_log.record_login(
                email=credentials.email, user_id=None, success=False,
                reason="invalid_credentials", ip=ip, user_agent=ua,
            )
        )
        raise HTTPException(
            status_code=401, detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    uid = str(user["_id"])

    # Blocked users cannot log in.
    if user.get("status") == "blocked":
        block = user.get("block") or {}
        reason = block.get("reason") or block.get("reason_code") or "policy violation"
        await run_in_threadpool(
            lambda: security_log.record_login(
                email=user["email"], user_id=uid, success=False,
                reason=f"blocked:{reason}", ip=ip, user_agent=ua,
            )
        )
        raise HTTPException(
            status_code=403,
            detail=f"Your account has been blocked ({reason}). Contact support for assistance.",
        )

    # Unverified email → require verification first.
    if not _is_verified(user):
        try:
            otp_result = await run_in_threadpool(otp_service.create_and_send, user["email"], "verify_email")
        except ValueError:
            otp_result = {"dev_code": None}
        await run_in_threadpool(
            lambda: security_log.record_login(
                email=user["email"], user_id=uid, success=False,
                reason="email_unverified", ip=ip, user_agent=ua,
            )
        )
        return {
            "requires_verification": True,
            "email": user["email"],
            "message": "Please verify your email to continue.",
            "dev_code": otp_result.get("dev_code"),
        }

    # 2FA enabled → email a login OTP, withhold the token.
    if _twofa_enabled(user):
        try:
            otp_result = await run_in_threadpool(otp_service.create_and_send, user["email"], "login_2fa")
        except ValueError as e:
            raise HTTPException(status_code=429, detail=str(e))
        await run_in_threadpool(
            lambda: security_log.record_login(
                email=user["email"], user_id=uid, success=False,
                reason="2fa_challenge", stage="2fa", ip=ip, user_agent=ua,
            )
        )
        return {
            "requires_2fa": True,
            "email": user["email"],
            "message": "Enter the verification code sent to your email.",
            "dev_code": otp_result.get("dev_code"),
        }

    # Success.
    await run_in_threadpool(
        lambda: security_log.record_login(
            email=user["email"], user_id=uid, success=True, reason="password", ip=ip, user_agent=ua,
        )
    )
    return _issue_token(user)


@router.post("/verify-2fa", response_model=Token)
async def verify_2fa(body: Verify2FARequest, request: Request):
    ip, ua = _client_info(request)
    user = await run_in_threadpool(lambda: users_collection.find_one({"email": body.email}))
    if not user:
        raise HTTPException(status_code=404, detail="Account not found")
    try:
        await run_in_threadpool(otp_service.verify, body.email, body.code, "login_2fa")
    except ValueError as e:
        await run_in_threadpool(
            lambda: security_log.record_login(
                email=body.email, user_id=str(user["_id"]), success=False,
                reason="2fa_invalid", stage="2fa", ip=ip, user_agent=ua,
            )
        )
        raise HTTPException(status_code=400, detail=str(e))

    await run_in_threadpool(
        lambda: security_log.record_login(
            email=body.email, user_id=str(user["_id"]), success=True,
            reason="2fa", stage="2fa", ip=ip, user_agent=ua,
        )
    )
    return _issue_token(user)


@router.post("/resend-otp")
async def resend_otp(body: ResendOtpRequest):
    user = await run_in_threadpool(lambda: users_collection.find_one({"email": body.email}))
    if not user:
        # Don't reveal whether the account exists.
        return {"sent": False, "message": "If the account exists, a code has been sent."}
    try:
        result = await run_in_threadpool(otp_service.create_and_send, body.email, body.purpose)
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))
    return {
        "sent": result.get("sent", False),
        "dev_code": result.get("dev_code"),
        "message": "A new code has been sent.",
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_full_current_user)):
    """Get current user information (fetches full profile from Mongo)."""
    return UserResponse(
        id=current_user["id"],
        email=current_user["email"],
        username=current_user["username"],
        full_name=current_user.get("full_name"),
        role=UserRole(current_user["role"]),
        created_at=current_user["created_at"],
    )

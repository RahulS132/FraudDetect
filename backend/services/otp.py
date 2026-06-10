"""One-time-passcode (OTP) service for email verification and login 2FA.

Codes are 6 digits, stored **hashed** (SHA-256) in `email_verifications` with an
expiry, an attempt counter, and a used flag. A TTL index on `expires_at` reaps
expired documents automatically. Rate limiting prevents rapid resends and caps
verification attempts per code.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any

from database import email_verifications_collection
from config import get_settings
from services import email as email_service

settings = get_settings()


def _hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def create_and_send(email: str, purpose: str) -> Dict[str, Any]:
    """Generate a code, store it hashed, send it. Raises ValueError if rate-limited.

    Returns {"sent": bool, "dev": bool, "dev_code": str|None}. ``dev_code`` is only
    populated when SMTP is unconfigured and OTP_DEV_ECHO is on, so the flow is
    testable locally without an email provider.
    """
    now = datetime.utcnow()
    last = email_verifications_collection.find_one(
        {"email": email, "purpose": purpose}, sort=[("created_at", -1)]
    )
    if last and last.get("created_at"):
        elapsed = (now - last["created_at"]).total_seconds()
        if elapsed < settings.OTP_RESEND_WINDOW_SECONDS:
            wait = int(settings.OTP_RESEND_WINDOW_SECONDS - elapsed)
            raise ValueError(f"Please wait {wait}s before requesting another code")

    code = f"{secrets.randbelow(10**6):06d}"
    # Invalidate any prior unused codes for this purpose so only the latest works.
    email_verifications_collection.update_many(
        {"email": email, "purpose": purpose, "used": False},
        {"$set": {"used": True}},
    )
    email_verifications_collection.insert_one({
        "email": email,
        "purpose": purpose,
        "code_hash": _hash(code),
        "attempts": 0,
        "used": False,
        "created_at": now,
        "expires_at": now + timedelta(minutes=settings.OTP_EXP_MINUTES),
    })

    result = email_service.send_otp_email(email, code, purpose)
    dev = bool(result.get("dev"))
    return {
        "sent": bool(result.get("sent")),
        "dev": dev,
        "dev_code": code if (dev and settings.OTP_DEV_ECHO) else None,
        "error": result.get("error"),
    }


def verify(email: str, code: str, purpose: str) -> bool:
    """Verify a code. Raises ValueError with a user-facing message on failure."""
    now = datetime.utcnow()
    doc = email_verifications_collection.find_one(
        {"email": email, "purpose": purpose, "used": False},
        sort=[("created_at", -1)],
    )
    if not doc:
        raise ValueError("No active code found. Please request a new one.")
    if doc.get("expires_at") and doc["expires_at"] < now:
        raise ValueError("This code has expired. Please request a new one.")
    if int(doc.get("attempts", 0)) >= settings.OTP_MAX_ATTEMPTS:
        email_verifications_collection.update_one({"_id": doc["_id"]}, {"$set": {"used": True}})
        raise ValueError("Too many attempts. Please request a new code.")
    if doc["code_hash"] != _hash(str(code).strip()):
        email_verifications_collection.update_one({"_id": doc["_id"]}, {"$inc": {"attempts": 1}})
        remaining = settings.OTP_MAX_ATTEMPTS - int(doc.get("attempts", 0)) - 1
        raise ValueError(f"Invalid code. {max(0, remaining)} attempt(s) remaining.")

    email_verifications_collection.update_one({"_id": doc["_id"]}, {"$set": {"used": True}})
    return True

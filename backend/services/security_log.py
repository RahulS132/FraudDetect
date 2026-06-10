"""Login attempt / history service.

Records every login attempt (success or failure) with IP, device (user-agent),
and the outcome, so admins can audit account access and force/disable 2FA from an
informed position.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any, List

from database import login_attempts_collection


def record_login(
    *,
    email: str,
    user_id: Optional[str],
    success: bool,
    reason: str = "",
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    stage: str = "password",
) -> None:
    try:
        login_attempts_collection.insert_one({
            "email": email,
            "user_id": user_id,
            "success": success,
            "reason": reason,
            "stage": stage,            # password | 2fa | verify_email
            "ip": ip,
            "user_agent": user_agent,
            "created_at": datetime.utcnow(),
        })
    except Exception as e:  # pragma: no cover - defensive
        print(f"[security_log] failed to record login: {e}")


def list_for_user(user_id: str, email: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {"$or": [{"user_id": user_id}]}
    if email:
        query["$or"].append({"email": email})
    docs = login_attempts_collection.find(query).sort("created_at", -1).limit(limit)
    out = []
    for d in docs:
        out.append({
            "id": str(d["_id"]),
            "email": d.get("email"),
            "success": bool(d.get("success")),
            "reason": d.get("reason", ""),
            "stage": d.get("stage", "password"),
            "ip": d.get("ip"),
            "user_agent": d.get("user_agent"),
            "created_at": d.get("created_at"),
        })
    return out

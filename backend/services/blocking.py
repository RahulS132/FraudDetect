"""User blocking / account-status service.

Manages the `status` field on users (active / suspended / blocked /
under_review), keeps a `block` sub-document with the active/last block details,
and writes a full history to `user_status_events` plus the security `audit_logs`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId

from database import users_collection, user_status_events_collection
from models import AccountStatus
from services import audit


def _record_status_event(
    user_id: str, action: str, actor: Dict[str, Any],
    reason_code: Optional[str] = None, reason: Optional[str] = None,
    notes: Optional[str] = None,
) -> None:
    user_status_events_collection.insert_one({
        "user_id": user_id,
        "action": action,
        "reason_code": reason_code,
        "reason": reason,
        "notes": notes,
        "actor_id": actor.get("id"),
        "actor_email": actor.get("email"),
        "created_at": datetime.utcnow(),
    })


def _get(user_id: str) -> Dict[str, Any]:
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise ValueError("User not found")
    return user


def block_user(user_id: str, *, reason_code: str, reason: Optional[str],
               notes: Optional[str], actor: Dict[str, Any]) -> Dict[str, Any]:
    user = _get(user_id)
    if user.get("role") == "admin":
        raise ValueError("Cannot block an admin account")
    now = datetime.utcnow()
    block = {
        "reason_code": reason_code,
        "reason": reason,
        "notes": notes,
        "blocked_by": actor.get("id"),
        "blocked_by_email": actor.get("email"),
        "blocked_at": now,
        "unblocked_by": None,
        "unblocked_at": None,
        "unblock_notes": None,
    }
    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"status": AccountStatus.BLOCKED.value, "block": block}},
    )
    _record_status_event(user_id, "block", actor, reason_code, reason, notes)
    audit.record("user_blocked", actor.get("id"), actor.get("email"), user_id,
                 {"reason_code": reason_code, "reason": reason, "notes": notes})
    return {"status": AccountStatus.BLOCKED.value, "block": block}


def unblock_user(user_id: str, *, notes: Optional[str], actor: Dict[str, Any]) -> Dict[str, Any]:
    user = _get(user_id)
    now = datetime.utcnow()
    existing = user.get("block") or {}
    existing.update({
        "unblocked_by": actor.get("id"),
        "unblocked_by_email": actor.get("email"),
        "unblocked_at": now,
        "unblock_notes": notes,
    })
    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"status": AccountStatus.ACTIVE.value, "block": existing}},
    )
    _record_status_event(user_id, "unblock", actor, notes=notes)
    audit.record("user_unblocked", actor.get("id"), actor.get("email"), user_id,
                 {"notes": notes})
    return {"status": AccountStatus.ACTIVE.value, "block": existing}


def set_status(user_id: str, *, status: str, notes: Optional[str], actor: Dict[str, Any]) -> Dict[str, Any]:
    user = _get(user_id)
    if status == AccountStatus.BLOCKED.value:
        raise ValueError("Use the block endpoint to block a user")
    if user.get("role") == "admin" and status != AccountStatus.ACTIVE.value:
        raise ValueError("Cannot suspend/review an admin account")
    users_collection.update_one(
        {"_id": user["_id"]}, {"$set": {"status": status}}
    )
    _record_status_event(user_id, f"status_{status}", actor, notes=notes)
    audit.record("user_status_changed", actor.get("id"), actor.get("email"), user_id,
                 {"from": user.get("status", "active"), "to": status, "notes": notes})
    return {"status": status}


def get_history(user_id: str, limit: int = 100) -> list:
    docs = (
        user_status_events_collection.find({"user_id": user_id})
        .sort("created_at", -1).limit(limit)
    )
    out = []
    for d in docs:
        out.append({
            "id": str(d["_id"]),
            "user_id": d.get("user_id"),
            "action": d.get("action"),
            "reason_code": d.get("reason_code"),
            "reason": d.get("reason"),
            "notes": d.get("notes"),
            "actor_id": d.get("actor_id"),
            "actor_email": d.get("actor_email"),
            "created_at": d.get("created_at"),
        })
    return out


def is_blocked(user: Dict[str, Any]) -> bool:
    return user.get("status") == AccountStatus.BLOCKED.value


def can_transact(user: Dict[str, Any]) -> bool:
    """Blocked or suspended users cannot create/modify transactions."""
    return user.get("status", AccountStatus.ACTIVE.value) in (
        AccountStatus.ACTIVE.value, AccountStatus.UNDER_REVIEW.value
    )

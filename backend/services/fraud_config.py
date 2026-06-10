"""Fraud auto-block configuration + fraud-event logging.

A single settings document in `fraud_config` holds the admin-tunable thresholds.
When a transaction's fraud score crosses a threshold the creation pipeline calls
``record_fraud_event`` and (for blocks) flags the user's account.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId

from database import fraud_config_collection, fraud_events_collection, users_collection
from services import audit

_DEFAULTS = {
    "auto_block_threshold": 95.0,
    "auto_flag_threshold": 80.0,
    "flag_account_on_block": True,
    "notify_admins": True,
}


def get_config() -> Dict[str, Any]:
    doc = fraud_config_collection.find_one({"_id": "singleton"})
    cfg = dict(_DEFAULTS)
    if doc:
        for k in _DEFAULTS:
            if doc.get(k) is not None:
                cfg[k] = doc[k]
        cfg["updated_by"] = doc.get("updated_by")
        cfg["updated_at"] = doc.get("updated_at")
    return cfg


def update_config(patch: Dict[str, Any], actor: Dict[str, Any]) -> Dict[str, Any]:
    before = get_config()
    update = {k: v for k, v in patch.items() if v is not None}
    update["updated_by"] = actor.get("email") or actor.get("id")
    update["updated_at"] = datetime.utcnow()
    fraud_config_collection.update_one(
        {"_id": "singleton"}, {"$set": update}, upsert=True
    )
    after = get_config()
    audit.record(
        "fraud_threshold_changed", actor.get("id"), actor.get("email"), None,
        {"before": {k: before.get(k) for k in _DEFAULTS},
         "after": {k: after.get(k) for k in _DEFAULTS}},
    )
    return after


def decide(fraud_score: float) -> Dict[str, Any]:
    """Given a 0–100 fraud score, decide the auto action.

    Returns {"action": "block"|"flag"|"none", "threshold": float|None}.
    """
    cfg = get_config()
    if fraud_score >= cfg["auto_block_threshold"]:
        return {"action": "block", "threshold": cfg["auto_block_threshold"], "config": cfg}
    if fraud_score >= cfg["auto_flag_threshold"]:
        return {"action": "flag", "threshold": cfg["auto_flag_threshold"], "config": cfg}
    return {"action": "none", "threshold": None, "config": cfg}


def record_fraud_event(
    *,
    transaction_id: Optional[str],
    user_id: Optional[str],
    username: Optional[str] = None,
    fraud_score: float,
    severity: str,
    threshold: Optional[float],
    action: str,
    reason: Optional[str] = None,
) -> str:
    doc = {
        "transaction_id": transaction_id,
        "user_id": user_id,
        "username": username,
        "fraud_score": round(float(fraud_score), 2),
        "severity": severity,
        "threshold": threshold,
        "action": action,
        "reason": reason,
        "created_at": datetime.utcnow(),
    }
    res = fraud_events_collection.insert_one(doc)
    return str(res.inserted_id)


def flag_account(user_id: str, reason: str) -> None:
    """Move an account to under_review (only if currently active)."""
    try:
        users_collection.update_one(
            {"_id": ObjectId(user_id), "status": {"$in": ["active", None]}},
            {"$set": {"status": "under_review"}},
        )
    except Exception:
        pass


def list_events(limit: int = 100) -> list:
    docs = fraud_events_collection.find().sort("created_at", -1).limit(limit)
    out = []
    for d in docs:
        out.append({
            "id": str(d["_id"]),
            "transaction_id": d.get("transaction_id"),
            "user_id": d.get("user_id"),
            "username": d.get("username"),
            "fraud_score": d.get("fraud_score", 0.0),
            "severity": d.get("severity", "none"),
            "threshold": d.get("threshold"),
            "action": d.get("action", "flagged"),
            "reason": d.get("reason"),
            "created_at": d.get("created_at"),
        })
    return out

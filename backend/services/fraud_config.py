"""Fraud auto-block configuration + fraud-event logging.

A single settings document in `fraud_config` holds the admin-tunable thresholds.
When a transaction's fraud score crosses a threshold the creation pipeline calls
``record_fraud_event`` and (for blocks) flags the user's account.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId

from database import (
    fraud_config_collection, fraud_events_collection, users_collection,
    transactions_collection,
)
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


def _score_from_anomaly(anomaly_score) -> float:
    """Map an Isolation-Forest anomaly_score (lower = riskier) to a 0–100 score."""
    if anomaly_score is None:
        return 75.0
    return round(max(0.0, min(100.0, (0.5 - float(anomaly_score)) * 100.0)), 1)


def list_events(limit: int = 100) -> list:
    """Recent fraud events feed.

    Shows the most recent transactions flagged as fraud from ANY source (CSV
    uploads and manual/auto-blocked transactions), joined to the user, so the
    Fraud Config page always reflects real detections — not only auto-blocks.
    """
    try:
        txns = list(
            transactions_collection.find({"is_fraud": True})
            .sort("created_at", -1)
            .limit(limit)
        )
    except Exception:
        txns = []

    # Resolve usernames in one batch.
    from bson import ObjectId
    uid_set = {t.get("user_id") for t in txns if t.get("user_id")}
    name_map = {}
    if uid_set:
        oids = []
        for uid in uid_set:
            try:
                oids.append(ObjectId(uid))
            except Exception:
                continue
        for u in users_collection.find({"_id": {"$in": oids}}, {"username": 1}):
            name_map[str(u["_id"])] = u.get("username", "")

    out = []
    for t in txns:
        score = t.get("fraud_score")
        if score is None:
            score = _score_from_anomaly(t.get("anomaly_score"))
        blocked = bool(t.get("auto_blocked"))
        out.append({
            "id": str(t["_id"]),
            "transaction_id": str(t["_id"]),
            "user_id": t.get("user_id"),
            "username": name_map.get(t.get("user_id") or "", ""),
            "fraud_score": round(float(score), 1),
            "severity": t.get("severity") or "high",
            "threshold": None,
            "action": "blocked" if blocked else "flagged",
            "reason": (
                f"${float(t.get('Amount', 0)):,.2f} {t.get('txn_type', 'purchase')} flagged"
                + (" — auto-blocked" if blocked else "")
            ),
            "created_at": t.get("created_at"),
        })
    return out

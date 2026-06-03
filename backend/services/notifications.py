"""Notification service.

Creates notification documents and pushes them in real time over the SSE
broker. Used primarily for instant fraud alerts (to the affected user and to
all admins) but also for system / bulk-import messages.

A notification document::

    {
      "_id": ObjectId,
      "user_id":  "<recipient user id>" | None,   # None when audience == admins
      "audience": "<user id>" | "__admins__",      # routing key
      "type":     "fraud_alert" | "system" | "bulk_import",
      "title":    str,
      "message":  str,
      "severity": "none|low|medium|high|critical",
      "is_read":  bool,
      "transaction_id": str | None,
      "created_at": datetime,
    }
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from database import notifications_collection
from services.events import broker, ADMINS


def _serialize(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "user_id": doc.get("user_id"),
        "type": doc.get("type", "system"),
        "title": doc.get("title", ""),
        "message": doc.get("message", ""),
        "severity": doc.get("severity", "none"),
        "is_read": bool(doc.get("is_read", False)),
        "transaction_id": doc.get("transaction_id"),
        "created_at": doc.get("created_at", datetime.utcnow()),
    }


async def create_notification(
    *,
    audience: str,
    type: str,
    title: str,
    message: str,
    severity: str = "none",
    user_id: Optional[str] = None,
    transaction_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a notification and push it over SSE to its audience.

    ``audience`` is the routing key: a concrete user_id, or the ADMINS sentinel.
    For user-targeted notifications, pass audience=user_id and user_id=user_id.
    """
    doc = {
        "user_id": user_id,
        "audience": audience,
        "type": type,
        "title": title,
        "message": message,
        "severity": severity,
        "is_read": False,
        "transaction_id": transaction_id,
        "created_at": datetime.utcnow(),
    }
    result = notifications_collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    serialized = _serialize(doc)

    # Real-time push (best effort).
    await broker.publish(audience, "notification", serialized)
    return serialized


async def notify_fraud(
    *,
    user_id: Optional[str],
    username: Optional[str],
    amount: float,
    severity: str,
    transaction_id: str,
) -> None:
    """Fire fraud alerts to both the affected user (if any) and all admins."""
    amount_str = f"${amount:,.2f}"
    # Affected user
    if user_id:
        await create_notification(
            audience=user_id,
            user_id=user_id,
            type="fraud_alert",
            title="Potential fraud detected",
            message=f"A transaction of {amount_str} on your account was flagged as fraudulent.",
            severity=severity,
            transaction_id=transaction_id,
        )
    # Admins (broadcast)
    who = username or (user_id or "a user")
    await create_notification(
        audience=ADMINS,
        user_id=None,
        type="fraud_alert",
        title=f"Fraud flagged ({severity})",
        message=f"Transaction {amount_str} for {who} was flagged as fraudulent.",
        severity=severity,
        transaction_id=transaction_id,
    )


def list_for_recipient(
    *, user_id: str, is_admin: bool, limit: int = 50
) -> Dict[str, Any]:
    """Return recent notifications + unread count for a recipient.

    Users see notifications addressed to them. Admins additionally see the
    ADMINS broadcast stream.
    """
    audiences: List[str] = [user_id]
    if is_admin:
        audiences.append(ADMINS)

    query = {"audience": {"$in": audiences}}
    cursor = (
        notifications_collection.find(query)
        .sort("created_at", -1)
        .limit(limit)
    )
    items = [_serialize(d) for d in cursor]
    unread_count = notifications_collection.count_documents(
        {"audience": {"$in": audiences}, "is_read": False}
    )
    return {"items": items, "unread_count": unread_count}


def mark_read(
    *, user_id: str, is_admin: bool, notification_ids: Optional[List[str]]
) -> int:
    """Mark given notifications (or all in scope) as read. Returns modified count."""
    audiences: List[str] = [user_id]
    if is_admin:
        audiences.append(ADMINS)

    query: Dict[str, Any] = {"audience": {"$in": audiences}, "is_read": False}
    if notification_ids:
        oids = []
        for nid in notification_ids:
            try:
                oids.append(ObjectId(nid))
            except Exception:
                continue
        query["_id"] = {"$in": oids}

    result = notifications_collection.update_many(query, {"$set": {"is_read": True}})
    return result.modified_count

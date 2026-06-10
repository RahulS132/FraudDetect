"""Audit logging service.

Every privileged / state-changing admin action (manual transaction creation,
bulk import, tag edits on another user's data) is recorded to the
``audit_logs`` collection so there is a tamper-evident trail of who did what to
whom and when.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from database import audit_logs_collection, users_collection


def record(
    action: str,
    actor_id: str,
    actor_email: Optional[str] = None,
    target_user_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> str:
    """Persist an audit entry. Returns the inserted id as a string.

    Failures here must never break the primary operation, so callers may wrap
    this in a try/except; we also guard internally.
    """
    doc = {
        "action": action,
        "actor_id": actor_id,
        "actor_email": actor_email,
        "target_user_id": target_user_id,
        "details": details or {},
        "created_at": datetime.utcnow(),
    }
    try:
        result = audit_logs_collection.insert_one(doc)
        return str(result.inserted_id)
    except Exception as e:  # pragma: no cover - defensive
        print(f"[audit] failed to record action={action}: {e}")
        return ""


def query(
    *,
    page: int = 1,
    page_size: int = 25,
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    target_user_id: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Searchable, paginated audit-log query for the admin audit page."""
    q: Dict[str, Any] = {}
    if action:
        q["action"] = action
    if actor_id:
        q["actor_id"] = actor_id
    if target_user_id:
        q["target_user_id"] = target_user_id
    if date_from or date_to:
        rng: Dict[str, Any] = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        q["created_at"] = rng
    if search:
        safe = re.escape(search)
        q["$or"] = [
            {"action": {"$regex": safe, "$options": "i"}},
            {"actor_email": {"$regex": safe, "$options": "i"}},
        ]

    total = audit_logs_collection.count_documents(q)
    page = max(1, page)
    page_size = max(1, min(200, page_size))
    cursor = (
        audit_logs_collection.find(q)
        .sort("created_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    docs = list(cursor)

    # Resolve target usernames in one batch.
    target_ids = {d.get("target_user_id") for d in docs if d.get("target_user_id")}
    name_map: Dict[str, str] = {}
    if target_ids:
        oids = []
        for tid in target_ids:
            try:
                oids.append(ObjectId(tid))
            except Exception:
                continue
        for u in users_collection.find({"_id": {"$in": oids}}, {"username": 1}):
            name_map[str(u["_id"])] = u.get("username", "")

    items: List[Dict[str, Any]] = []
    for d in docs:
        items.append({
            "id": str(d["_id"]),
            "action": d.get("action", ""),
            "actor_id": d.get("actor_id"),
            "actor_email": d.get("actor_email"),
            "target_user_id": d.get("target_user_id"),
            "target_username": name_map.get(d.get("target_user_id") or ""),
            "details": d.get("details", {}),
            "created_at": d.get("created_at"),
        })
    total_pages = (total + page_size - 1) // page_size if total else 0
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }

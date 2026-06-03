"""Audit logging service.

Every privileged / state-changing admin action (manual transaction creation,
bulk import, tag edits on another user's data) is recorded to the
``audit_logs`` collection so there is a tamper-evident trail of who did what to
whom and when.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from database import audit_logs_collection


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

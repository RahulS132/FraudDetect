"""Admin transaction-rules + fraud-config + fraud-events + audit routes.

    GET    /api/admin/transaction-rules
    POST   /api/admin/transaction-rules
    PATCH  /api/admin/transaction-rules/{id}
    POST   /api/admin/transaction-rules/{id}/toggle
    DELETE /api/admin/transaction-rules/{id}

    GET    /api/admin/fraud-config
    PATCH  /api/admin/fraud-config
    GET    /api/admin/fraud-events

    GET    /api/admin/audit-logs/search   (searchable, paginated)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from bson import ObjectId
from bson.errors import InvalidId

from models import (
    TransactionRuleCreate, TransactionRuleUpdate, TransactionRuleResponse,
    FraudConfigResponse, FraudConfigUpdate, FraudEventResponse,
    AuditLogListResponse,
)
from database import transaction_rules_collection
from auth import get_current_admin
from services import fraud_config as fraud_config_service
from services import audit

router = APIRouter(prefix="/api/admin", tags=["Admin - Rules & Fraud"])


def _oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid id format")


def _serialize_rule(d: dict) -> dict:
    return {
        "id": str(d["_id"]),
        "name": d.get("name", ""),
        "rule_type": d.get("rule_type", ""),
        "action": d.get("action", "block"),
        "enabled": bool(d.get("enabled", True)),
        "config": d.get("config", {}),
        "description": d.get("description"),
        "trigger_count": int(d.get("trigger_count", 0)),
        "created_by": d.get("created_by"),
        "created_at": d.get("created_at"),
        "updated_at": d.get("updated_at"),
    }


# ── transaction rules ────────────────────────────────────────────────────────

@router.get("/transaction-rules", response_model=List[TransactionRuleResponse])
async def list_rules(current_admin: dict = Depends(get_current_admin)):
    def _work():
        docs = list(transaction_rules_collection.find().sort("created_at", -1))
        return [_serialize_rule(d) for d in docs]
    return await run_in_threadpool(_work)


@router.post("/transaction-rules", response_model=TransactionRuleResponse, status_code=201)
async def create_rule(body: TransactionRuleCreate, current_admin: dict = Depends(get_current_admin)):
    now = datetime.utcnow()
    doc = {
        "name": body.name,
        "rule_type": body.rule_type.value,
        "action": body.action.value,
        "enabled": body.enabled,
        "config": body.config or {},
        "description": body.description,
        "trigger_count": 0,
        "created_by": current_admin.get("id"),
        "created_at": now,
        "updated_at": now,
    }

    def _work():
        res = transaction_rules_collection.insert_one(doc)
        doc["_id"] = res.inserted_id
        audit.record("transaction_rule_created", current_admin.get("id"),
                     current_admin.get("email"), None,
                     {"name": body.name, "rule_type": body.rule_type.value, "action": body.action.value})
        return _serialize_rule(doc)
    return await run_in_threadpool(_work)


@router.patch("/transaction-rules/{rule_id}", response_model=TransactionRuleResponse)
async def update_rule(rule_id: str, body: TransactionRuleUpdate, current_admin: dict = Depends(get_current_admin)):
    oid = _oid(rule_id)
    update = {}
    if body.name is not None:
        update["name"] = body.name
    if body.rule_type is not None:
        update["rule_type"] = body.rule_type.value
    if body.action is not None:
        update["action"] = body.action.value
    if body.enabled is not None:
        update["enabled"] = body.enabled
    if body.config is not None:
        update["config"] = body.config
    if body.description is not None:
        update["description"] = body.description
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")
    update["updated_at"] = datetime.utcnow()

    def _work():
        res = transaction_rules_collection.find_one_and_update(
            {"_id": oid}, {"$set": update}, return_document=True
        )
        if not res:
            raise HTTPException(status_code=404, detail="Rule not found")
        audit.record("transaction_rule_updated", current_admin.get("id"),
                     current_admin.get("email"), None, {"rule_id": rule_id, "changes": list(update.keys())})
        return _serialize_rule(res)
    return await run_in_threadpool(_work)


@router.post("/transaction-rules/{rule_id}/toggle", response_model=TransactionRuleResponse)
async def toggle_rule(rule_id: str, current_admin: dict = Depends(get_current_admin)):
    oid = _oid(rule_id)

    def _work():
        rule = transaction_rules_collection.find_one({"_id": oid})
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")
        new_enabled = not bool(rule.get("enabled", True))
        transaction_rules_collection.update_one(
            {"_id": oid}, {"$set": {"enabled": new_enabled, "updated_at": datetime.utcnow()}}
        )
        rule["enabled"] = new_enabled
        audit.record("transaction_rule_toggled", current_admin.get("id"),
                     current_admin.get("email"), None, {"rule_id": rule_id, "enabled": new_enabled})
        return _serialize_rule(rule)
    return await run_in_threadpool(_work)


@router.delete("/transaction-rules/{rule_id}")
async def delete_rule(rule_id: str, current_admin: dict = Depends(get_current_admin)):
    oid = _oid(rule_id)

    def _work():
        res = transaction_rules_collection.delete_one({"_id": oid})
        if res.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Rule not found")
        audit.record("transaction_rule_deleted", current_admin.get("id"),
                     current_admin.get("email"), None, {"rule_id": rule_id})
        return {"success": True}
    return await run_in_threadpool(_work)


# ── fraud config + events ────────────────────────────────────────────────────

@router.get("/fraud-config", response_model=FraudConfigResponse)
async def get_fraud_config(current_admin: dict = Depends(get_current_admin)):
    return await run_in_threadpool(fraud_config_service.get_config)


@router.patch("/fraud-config", response_model=FraudConfigResponse)
async def update_fraud_config(body: FraudConfigUpdate, current_admin: dict = Depends(get_current_admin)):
    patch = body.dict(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    return await run_in_threadpool(fraud_config_service.update_config, patch, current_admin)


@router.get("/fraud-events", response_model=List[FraudEventResponse])
async def list_fraud_events(
    current_admin: dict = Depends(get_current_admin),
    limit: int = Query(100, ge=1, le=500),
):
    return await run_in_threadpool(fraud_config_service.list_events, limit)


# ── searchable audit log ─────────────────────────────────────────────────────

@router.get("/audit-logs/search", response_model=AuditLogListResponse)
async def search_audit_logs(
    current_admin: dict = Depends(get_current_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    action: Optional[str] = None,
    actor_id: Optional[str] = None,
    target_user_id: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    return await run_in_threadpool(
        lambda: audit.query(
            page=page, page_size=page_size, action=action, actor_id=actor_id,
            target_user_id=target_user_id, search=search,
            date_from=date_from, date_to=date_to,
        )
    )

"""Admin transaction management & user-specific views.

Endpoints (all admin-only):
    GET  /api/admin/users                      list users + summary stats
    GET  /api/admin/users/{user_id}            single user summary
    GET  /api/admin/users/{user_id}/transactions   paginated, filterable tx list
    GET  /api/admin/users/{user_id}/analytics  risk score, spending, volume, trend
    POST /api/admin/transactions/bulk          create many transactions for a user
    GET  /api/admin/audit-logs                 recent admin audit trail
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.concurrency import run_in_threadpool
from bson import ObjectId
from bson.errors import InvalidId

from models import (
    BulkTransactionCreate,
    BulkCreateResult,
    AdminUserSummary,
    UserAnalytics,
)
from database import (
    users_collection,
    transactions_collection,
    detection_results_collection,
    audit_logs_collection,
)
from auth import get_current_admin
from fraud_detection import score_manual_transaction, severity_from_score
from services import notifications as notif_service
from services.events import broker

router = APIRouter(prefix="/api/admin", tags=["Admin - Transactions"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _valid_object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid id format")


def _risk_level(score: float) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


# ── user listing + summary ───────────────────────────────────────────────────

@router.get("/users", response_model=List[AdminUserSummary])
async def list_users(
    current_admin: dict = Depends(get_current_admin),
    search: Optional[str] = Query(None, description="Filter by username/email substring"),
):
    """List all users with per-user transaction + fraud summary for selection."""

    def _work() -> List[AdminUserSummary]:
        user_query: Dict[str, Any] = {}
        if search:
            user_query = {
                "$or": [
                    {"username": {"$regex": search, "$options": "i"}},
                    {"email": {"$regex": search, "$options": "i"}},
                    {"full_name": {"$regex": search, "$options": "i"}},
                ]
            }
        users = list(users_collection.find(user_query))

        # Aggregate tx + fraud counts per user in one pass.
        stats_pipeline = [
            {
                "$group": {
                    "_id": "$user_id",
                    "total": {"$sum": 1},
                    "fraud": {"$sum": {"$cond": [{"$eq": ["$is_fraud", True]}, 1, 0]}},
                }
            }
        ]
        stats_map = {
            r["_id"]: r for r in detection_results_collection.aggregate(stats_pipeline)
        }

        out: List[AdminUserSummary] = []
        for u in users:
            uid = str(u["_id"])
            s = stats_map.get(uid, {})
            total = int(s.get("total", 0))
            fraud = int(s.get("fraud", 0))
            out.append(
                AdminUserSummary(
                    user_id=uid,
                    username=u.get("username", ""),
                    email=u.get("email", ""),
                    full_name=u.get("full_name"),
                    role=u.get("role", "user"),
                    created_at=u.get("created_at", datetime.utcnow()),
                    total_transactions=total,
                    fraud_count=fraud,
                    fraud_rate=round(fraud / total * 100, 2) if total else 0.0,
                )
            )
        # Most active first.
        out.sort(key=lambda x: x.total_transactions, reverse=True)
        return out

    return await run_in_threadpool(_work)


@router.get("/users/{user_id}", response_model=AdminUserSummary)
async def get_user_summary(
    user_id: str, current_admin: dict = Depends(get_current_admin)
):
    oid = _valid_object_id(user_id)

    def _work() -> AdminUserSummary:
        u = users_collection.find_one({"_id": oid})
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        agg = list(
            detection_results_collection.aggregate(
                [
                    {"$match": {"user_id": user_id}},
                    {
                        "$group": {
                            "_id": None,
                            "total": {"$sum": 1},
                            "fraud": {
                                "$sum": {"$cond": [{"$eq": ["$is_fraud", True]}, 1, 0]}
                            },
                        }
                    },
                ]
            )
        )
        total = int(agg[0]["total"]) if agg else 0
        fraud = int(agg[0]["fraud"]) if agg else 0
        return AdminUserSummary(
            user_id=user_id,
            username=u.get("username", ""),
            email=u.get("email", ""),
            full_name=u.get("full_name"),
            role=u.get("role", "user"),
            created_at=u.get("created_at", datetime.utcnow()),
            total_transactions=total,
            fraud_count=fraud,
            fraud_rate=round(fraud / total * 100, 2) if total else 0.0,
        )

    return await run_in_threadpool(_work)


# ── per-user paginated transaction list ──────────────────────────────────────

@router.get("/users/{user_id}/transactions")
async def get_user_transactions(
    user_id: str,
    current_admin: dict = Depends(get_current_admin),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    fraud_status: Optional[str] = Query(None, regex="^(fraud|approved)$"),
    tag: Optional[str] = None,
    sort_by: str = Query("created_at", regex="^(created_at|amount|fraud_score)$"),
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
):
    """Paginated, filterable transaction history for one user (admin view)."""
    _valid_object_id(user_id)
    from services.search import query_transactions  # local import to avoid cycle

    return await run_in_threadpool(
        query_transactions,
        scope_user_id=user_id,
        page=page,
        page_size=page_size,
        fraud_status=fraud_status,
        tag=tag,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


# ── per-user analytics (risk score, spending, volume, trend) ─────────────────

@router.get("/users/{user_id}/analytics", response_model=UserAnalytics)
async def get_user_analytics(
    user_id: str, current_admin: dict = Depends(get_current_admin)
):
    oid = _valid_object_id(user_id)

    def _work() -> UserAnalytics:
        u = users_collection.find_one({"_id": oid})
        if not u:
            raise HTTPException(status_code=404, detail="User not found")

        # Detection stats
        det_agg = list(
            detection_results_collection.aggregate(
                [
                    {"$match": {"user_id": user_id}},
                    {
                        "$group": {
                            "_id": None,
                            "total": {"$sum": 1},
                            "approved": {
                                "$sum": {"$cond": [{"$eq": ["$is_approved", True]}, 1, 0]}
                            },
                            "fraud": {
                                "$sum": {"$cond": [{"$eq": ["$is_fraud", True]}, 1, 0]}
                            },
                            "avg_score": {"$avg": "$anomaly_score"},
                        }
                    },
                ]
            )
        )
        total = int(det_agg[0]["total"]) if det_agg else 0
        approved = int(det_agg[0]["approved"]) if det_agg else 0
        fraud = int(det_agg[0]["fraud"]) if det_agg else 0
        avg_score = float(det_agg[0]["avg_score"]) if det_agg and det_agg[0]["avg_score"] is not None else 0.0
        rejected = total - approved
        legit = total - fraud
        fraud_pct = round(fraud / total * 100, 2) if total else 0.0
        approval_rate = round(approved / total * 100, 2) if total else 0.0

        # Volume from transactions
        vol_agg = list(
            transactions_collection.aggregate(
                [
                    {"$match": {"user_id": user_id}},
                    {
                        "$group": {
                            "_id": None,
                            "total_volume": {"$sum": "$Amount"},
                            "avg_amount": {"$avg": "$Amount"},
                        }
                    },
                ]
            )
        )
        total_volume = float(vol_agg[0]["total_volume"]) if vol_agg else 0.0
        avg_amount = float(vol_agg[0]["avg_amount"]) if vol_agg and vol_agg[0]["avg_amount"] is not None else 0.0

        # Spending by tag
        tag_agg = list(
            transactions_collection.aggregate(
                [
                    {"$match": {"user_id": user_id}},
                    {
                        "$group": {
                            "_id": {"$ifNull": ["$tag", "Untagged"]},
                            "count": {"$sum": 1},
                            "amount": {"$sum": "$Amount"},
                        }
                    },
                    {"$sort": {"amount": -1}},
                ]
            )
        )
        spending_by_tag = [
            {"tag": r["_id"], "count": int(r["count"]), "amount": round(float(r["amount"]), 2)}
            for r in tag_agg
        ]

        # Transactions over time
        time_agg = list(
            detection_results_collection.aggregate(
                [
                    {"$match": {"user_id": user_id}},
                    {
                        "$group": {
                            "_id": {
                                "$dateToString": {
                                    "format": "%Y-%m-%d",
                                    "date": "$created_at",
                                }
                            },
                            "total": {"$sum": 1},
                            "fraud": {
                                "$sum": {"$cond": [{"$eq": ["$is_fraud", True]}, 1, 0]}
                            },
                        }
                    },
                    {"$sort": {"_id": 1}},
                ]
            )
        )
        transactions_over_time = {
            "dates": [r["_id"] for r in time_agg],
            "total_counts": [r["total"] for r in time_agg],
            "fraud_counts": [r["fraud"] for r in time_agg],
        }

        # Composite risk score (0–100): weighted blend of fraud rate and how
        # anomalous the user's average score is (lower avg_score → riskier).
        # Normalise avg_score from a typical [-0.5, 0.2] range to [0, 1].
        score_component = max(0.0, min(1.0, (0.2 - avg_score) / 0.7)) * 100
        risk_score = round(min(100.0, fraud_pct * 0.7 + score_component * 0.3), 2)

        return UserAnalytics(
            user_id=user_id,
            username=u.get("username", ""),
            email=u.get("email", ""),
            full_name=u.get("full_name"),
            total_transactions=total,
            approved_transactions=approved,
            rejected_transactions=rejected,
            fraud_detected=fraud,
            legitimate_transactions=legit,
            fraud_percentage=fraud_pct,
            approval_rate=approval_rate,
            total_volume=round(total_volume, 2),
            avg_transaction=round(avg_amount, 2),
            risk_score=risk_score,
            risk_level=_risk_level(risk_score),
            spending_by_tag=spending_by_tag,
            transactions_over_time=transactions_over_time,
        )

    return await run_in_threadpool(_work)


# ── bulk transaction creation ────────────────────────────────────────────────

@router.post(
    "/transactions/bulk",
    response_model=BulkCreateResult,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_transactions(
    payload: BulkTransactionCreate,
    current_admin: dict = Depends(get_current_admin),
):
    """Create one or many transactions for a target user.

    Each row is validated (Pydantic) and scored with the rule-based heuristic.
    Fraud-flagged rows generate real-time notifications to the user and admins.
    The whole batch is recorded in the audit log.
    """
    target_oid = _valid_object_id(payload.user_id)

    # Validate the target user exists (in threadpool — pymongo is sync).
    target_user = await run_in_threadpool(
        lambda: users_collection.find_one({"_id": target_oid})
    )
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    target_username = target_user.get("username")
    now = datetime.utcnow()
    source = "admin_bulk" if len(payload.transactions) > 1 else "admin_manual"

    txn_docs: List[Dict[str, Any]] = []
    scored: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for idx, item in enumerate(payload.transactions):
        try:
            result = score_manual_transaction(
                amount=item.amount,
                is_fraud_override=item.is_fraud_override,
            )
            actual_class = 1 if item.is_fraud_override is True else 0
            txn_docs.append(
                {
                    "user_id": payload.user_id,
                    "Time": 0.0,
                    "Amount": float(item.amount),
                    "Class": int(actual_class),
                    "category": item.category,
                    "tag": item.tag.value if item.tag else None,
                    "description": item.description,
                    "creation_source": source,
                    "created_by": current_admin["id"],
                    "transaction_time": item.transaction_time or now,
                    "created_at": now,
                }
            )
            scored.append(result)
        except Exception as e:  # individual row failure shouldn't kill the batch
            errors.append({"index": idx, "error": str(e)})

    if not txn_docs:
        return BulkCreateResult(
            success=False,
            created_count=0,
            failed_count=len(errors),
            fraud_flagged=0,
            errors=errors,
        )

    # Denormalize the fraud fields onto each transaction so search/filter/sort
    # run on the transactions collection alone (no per-query join).
    for td, sc in zip(txn_docs, scored):
        td["is_fraud"] = sc["is_fraud"]
        td["is_approved"] = sc["is_approved"]
        td["anomaly_score"] = sc["anomaly_score"]
        td["actual_class"] = int(td["Class"])
        td["severity"] = sc["severity"]

    # Insert transactions, then detection results, in the threadpool.
    def _persist() -> List[ObjectId]:
        res = transactions_collection.insert_many(txn_docs)
        ids = res.inserted_ids
        det_docs = []
        for tid, sc, td in zip(ids, scored, txn_docs):
            det_docs.append(
                {
                    "transaction_id": str(tid),
                    "user_id": payload.user_id,
                    "is_fraud": sc["is_fraud"],
                    "is_approved": sc["is_approved"],
                    "anomaly_score": sc["anomaly_score"],
                    "actual_class": int(td["Class"]),
                    "severity": sc["severity"],
                    "created_at": now,
                }
            )
        detection_results_collection.insert_many(det_docs)
        return ids

    inserted_ids = await run_in_threadpool(_persist)
    fraud_flagged = sum(1 for s in scored if s["is_fraud"])

    # Audit log
    await run_in_threadpool(
        lambda: audit_logs_collection.insert_one(
            {
                "action": "bulk_create_transactions",
                "actor_id": current_admin["id"],
                "actor_email": current_admin.get("email"),
                "target_user_id": payload.user_id,
                "details": {
                    "count": len(inserted_ids),
                    "fraud_flagged": fraud_flagged,
                    "source": source,
                },
                "created_at": now,
            }
        )
    )

    # Real-time fraud notifications + dashboard refresh events.
    for tid, item, sc in zip(inserted_ids, payload.transactions, scored):
        if sc["is_fraud"]:
            await notif_service.notify_fraud(
                user_id=payload.user_id,
                username=target_username,
                amount=item.amount,
                severity=sc["severity"],
                transaction_id=str(tid),
            )

    # Tell the affected user and all admins their data changed.
    await broker.publish_to_user(
        payload.user_id, "transactions_updated", {"reason": "bulk_create"}
    )
    await broker.publish_to_admins(
        "transactions_updated",
        {"reason": "bulk_create", "user_id": payload.user_id, "count": len(inserted_ids)},
    )

    return BulkCreateResult(
        success=True,
        created_count=len(inserted_ids),
        failed_count=len(errors),
        fraud_flagged=fraud_flagged,
        errors=errors,
        transaction_ids=[str(i) for i in inserted_ids],
    )


# ── audit log ────────────────────────────────────────────────────────────────

@router.get("/audit-logs")
async def get_audit_logs(
    current_admin: dict = Depends(get_current_admin),
    limit: int = Query(100, ge=1, le=500),
):
    def _work():
        docs = list(
            audit_logs_collection.find().sort("created_at", -1).limit(limit)
        )
        out = []
        for d in docs:
            out.append(
                {
                    "id": str(d["_id"]),
                    "action": d.get("action"),
                    "actor_id": d.get("actor_id"),
                    "actor_email": d.get("actor_email"),
                    "target_user_id": d.get("target_user_id"),
                    "details": d.get("details", {}),
                    "created_at": d.get("created_at"),
                }
            )
        return out

    return await run_in_threadpool(_work)

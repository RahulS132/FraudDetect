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
    is_credit_txn,
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
from services import account as account_service
from services import rules_engine
from services import fraud_config as fraud_config_service
from services import blocking as blocking_service
from services.events import broker, ADMINS

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
        # This month's spend per user (one aggregation) → monthly utilization.
        spend_map = account_service.monthly_spend_map()

        out: List[AdminUserSummary] = []
        for u in users:
            uid = str(u["_id"])
            s = stats_map.get(uid, {})
            total = int(s.get("total", 0))
            fraud = int(s.get("fraud", 0))
            acct = account_service.compute_summary(u, spend_map.get(uid, 0.0))
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
                    status=acct["status"],
                    credit_limit=acct["credit_limit"],
                    current_balance=acct["current_balance"],
                    available_credit=acct["available_credit"],
                    credit_utilization=acct["credit_utilization"],
                    is_frozen=acct["is_frozen"],
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
        acct = account_service.compute_summary(u, account_service.monthly_spend(user_id))
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
            status=acct["status"],
            credit_limit=acct["credit_limit"],
            current_balance=acct["current_balance"],
            available_credit=acct["available_credit"],
            credit_utilization=acct["credit_utilization"],
            is_frozen=acct["is_frozen"],
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

    # Blocked / suspended users cannot have transactions created against them.
    if not blocking_service.can_transact(target_user):
        raise HTTPException(
            status_code=403,
            detail=f"User account is {target_user.get('status', 'blocked')} — transactions are not permitted",
        )

    target_username = target_user.get("username")
    now = datetime.utcnow()
    source = "admin_bulk" if len(payload.transactions) > 1 else "admin_manual"

    # ── Enforcement pipeline (runs entirely in the threadpool) ───────────────
    # Per transaction, in order:
    #   1. Transaction rules engine  → hard-block matches are rejected.
    #   2. Fraud scoring + auto-block → score ≥ threshold blocks + flags account.
    #   3. Balance / credit check     → approved spends that exceed available
    #                                    credit (or hit a frozen/suspended
    #                                    account) are rejected with a reason.
    # Approved spends are committed to the user's balance with before/after
    # recorded on each transaction. Every rejection is written to the audit log.
    fraud_cfg = await run_in_threadpool(fraud_config_service.get_config)

    def _process() -> Dict[str, Any]:
        acct = account_service.compute_summary(target_user)
        credit_limit = acct["credit_limit"]
        has_limit = acct["has_credit_limit"]         # False → unlimited credit
        running_balance = acct["current_balance"]   # spendable cash
        running_credit_used = acct["credit_used"]
        frozen = acct["is_frozen"]
        suspended = acct["credit_suspended"]

        # Per-account history feeds the fraud algorithm (z-score + velocity).
        stats = account_service.user_amount_stats(payload.user_id)
        user_mean, user_std = stats["mean"], stats["std"]
        running_recent = int(stats["recent_count"])  # grows as we add debits

        def avail_credit() -> float:
            return 0.0 if suspended else max(0.0, round(credit_limit - running_credit_used, 2))

        def spending_power() -> float:
            return round(running_balance + avail_credit(), 2)

        txn_docs: List[Dict[str, Any]] = []
        scored: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        notify: List[Dict[str, Any]] = []        # fraud notifications to fire
        rejections: List[Dict[str, Any]] = []     # audit entries for rejects
        flag_account = False
        spend_total = 0.0           # debit amount (money out, posted)
        deposit_total = 0.0         # credit amount (money in)
        posted_count = 0            # money-moving txns (deposits + approved debits)
        balance_used_total = 0.0
        credit_drawn_total = 0.0

        for idx, item in enumerate(payload.transactions):
            try:
                amt = float(item.amount)
                ttype = item.txn_type.value if item.txn_type else "purchase"
                is_credit = is_credit_txn(ttype)   # deposit / refund → money in
                balance_before = round(running_balance, 2)

                # ── Money IN (deposit / refund): no fraud scoring, just credit ──
                if is_credit:
                    running_balance = round(running_balance + amt, 2)
                    balance_after = running_balance
                    deposit_total += amt
                    posted_count += 1
                    td = {
                        "user_id": payload.user_id, "Time": 0.0, "Amount": amt, "Class": 0,
                        "txn_type": ttype, "direction": "credit",
                        "category": item.category, "tag": item.tag.value if item.tag else None,
                        "description": item.description, "merchant": item.merchant,
                        "country": item.country, "card_type": item.card_type,
                        "creation_source": source, "created_by": current_admin["id"],
                        "transaction_time": item.transaction_time or now, "created_at": now,
                        "is_fraud": False, "is_approved": True, "anomaly_score": 0.5,
                        "actual_class": 0, "severity": "none", "fraud_score": 0.0,
                        "auto_blocked": False, "flagged": False,
                        "balance_before": balance_before, "balance_after": balance_after,
                    }
                    txn_docs.append(td)
                    scored.append({"is_fraud": False, "fraud_score": 0.0, "severity": "none",
                                   "anomaly_score": 0.5, "auto_blocked": False,
                                   "auto_flagged": False, "threshold": None})
                    continue

                # ── Money OUT (purchase / withdrawal): full enforcement ──────────
                txn_ctx = {
                    "amount": amt, "merchant": item.merchant, "category": item.category,
                    "tag": item.tag.value if item.tag else None, "country": item.country,
                    "card_type": item.card_type, "user_id": payload.user_id,
                }

                # 1) Rules engine
                rule_res = rules_engine.evaluate(txn_ctx)
                if rule_res["blocked"]:
                    errors.append({"index": idx, "error": rule_res["reason"], "kind": "rule_block"})
                    rejections.append({"index": idx, "reason": rule_res["reason"], "type": "rule_block"})
                    continue
                flagged_by_rule = bool(rule_res["flags"])

                # 2) Fraud scoring (per-account anomaly + velocity) + auto decision
                sc = score_manual_transaction(
                    amount=amt, is_fraud_override=item.is_fraud_override,
                    category=item.category or "Other",
                    transaction_time=item.transaction_time,
                    recent_count=running_recent,
                    user_mean=user_mean, user_std=user_std,
                )
                running_recent += 1   # each debit raises this account's velocity
                decision = fraud_config_service.decide(sc["fraud_score"])
                auto_blocked = decision["action"] == "block"
                auto_flagged = decision["action"] == "flag" or flagged_by_rule

                if auto_blocked:
                    sc["is_fraud"] = True
                    sc["is_approved"] = False
                    sc["severity"] = "critical" if sc["severity"] == "none" else sc["severity"]

                approved = sc["is_approved"] and not auto_blocked

                # 3) Balance / credit check (only for spends that would post).
                balance_after = balance_before
                if approved:
                    if frozen:
                        errors.append({"index": idx, "error": "Account balance is frozen", "kind": "balance"})
                        rejections.append({"index": idx, "reason": "frozen", "type": "balance_reject"})
                        continue
                    # No credit limit applied → unlimited credit; skip the ceiling check.
                    if has_limit and amt > spending_power():
                        msg = (f"Transaction ${amt:,.2f} exceeds available funds "
                               f"${spending_power():,.2f} (balance ${running_balance:,.2f} + credit ${avail_credit():,.2f})")
                        errors.append({"index": idx, "error": msg, "kind": "balance"})
                        rejections.append({"index": idx, "reason": msg, "type": "balance_reject"})
                        continue
                    # accept: cash first, then credit for the remainder
                    from_balance = min(running_balance, amt)
                    running_balance = round(running_balance - from_balance, 2)
                    remainder = round(amt - from_balance, 2)
                    running_credit_used = round(running_credit_used + remainder, 2)
                    balance_after = running_balance
                    balance_used_total += from_balance
                    credit_drawn_total += remainder
                    spend_total += amt
                    posted_count += 1
                # Fraud/blocked debits are still recorded but don't post to balance.

                actual_class = 1 if (item.is_fraud_override is True or auto_blocked) else int(sc.get("is_fraud", False))
                td = {
                    "user_id": payload.user_id,
                    "Time": 0.0,
                    "Amount": amt,
                    "Class": int(actual_class),
                    "txn_type": ttype,
                    "direction": "debit",
                    "category": item.category,
                    "tag": item.tag.value if item.tag else None,
                    "description": item.description,
                    "merchant": item.merchant,
                    "country": item.country,
                    "card_type": item.card_type,
                    "creation_source": source,
                    "created_by": current_admin["id"],
                    "transaction_time": item.transaction_time or now,
                    "created_at": now,
                    "is_fraud": sc["is_fraud"],
                    "is_approved": sc["is_approved"] and not auto_blocked,
                    "anomaly_score": sc["anomaly_score"],
                    "actual_class": int(actual_class),
                    "severity": sc["severity"],
                    "fraud_score": sc["fraud_score"],
                    "auto_blocked": auto_blocked,
                    "flagged": auto_flagged,
                    "balance_before": balance_before,
                    "balance_after": balance_after,
                }
                txn_docs.append(td)
                scored.append({**sc, "auto_blocked": auto_blocked, "auto_flagged": auto_flagged,
                               "threshold": decision["threshold"]})
            except Exception as e:
                errors.append({"index": idx, "error": str(e), "kind": "validation"})

        if not txn_docs:
            # Still audit the rejections.
            if rejections:
                audit_logs_collection.insert_one({
                    "action": "bulk_create_rejected",
                    "actor_id": current_admin["id"],
                    "actor_email": current_admin.get("email"),
                    "target_user_id": payload.user_id,
                    "details": {"rejections": rejections, "source": source},
                    "created_at": now,
                })
            return {
                "ids": [], "scored": [], "errors": errors, "fraud_flagged": 0,
                "notify": [], "posted_count": 0, "rejections": rejections,
            }

        # Insert transactions + detection results.
        res = transactions_collection.insert_many(txn_docs)
        ids = res.inserted_ids
        det_docs = []
        for tid, sc, td in zip(ids, scored, txn_docs):
            det_docs.append({
                "transaction_id": str(tid),
                "user_id": payload.user_id,
                "is_fraud": sc["is_fraud"],
                "is_approved": td["is_approved"],
                "anomaly_score": sc["anomaly_score"],
                "actual_class": int(td["Class"]),
                "severity": sc["severity"],
                "created_at": now,
            })
        detection_results_collection.insert_many(det_docs)

        # Commit the batch's money movements (debits out, deposits in) in one
        # write, using the exact running balance/credit computed above.
        if posted_count:
            account_service.commit_batch(
                payload.user_id,
                final_balance=running_balance, final_credit_used=running_credit_used,
                deposit_total=deposit_total, spend_total=spend_total, count=posted_count,
            )

        # Fraud events + account flagging + notification list.
        for tid, sc in zip(ids, scored):
            if sc.get("auto_blocked"):
                fraud_config_service.record_fraud_event(
                    transaction_id=str(tid), user_id=payload.user_id,
                    username=target_username, fraud_score=sc["fraud_score"],
                    severity=sc["severity"], threshold=sc.get("threshold"),
                    action="blocked",
                    reason=f"Fraud score {sc['fraud_score']} ≥ auto-block threshold {sc.get('threshold')}",
                )
                if fraud_cfg.get("flag_account_on_block"):
                    flag_account = True
                notify.append({"transaction_id": str(tid), "severity": sc["severity"],
                               "amount": None, "auto_blocked": True})
            elif sc.get("auto_flagged") or sc.get("is_fraud"):
                action = "flagged"
                fraud_config_service.record_fraud_event(
                    transaction_id=str(tid), user_id=payload.user_id,
                    username=target_username, fraud_score=sc["fraud_score"],
                    severity=sc["severity"], threshold=sc.get("threshold"),
                    action=action, reason="Flagged for review",
                )
                notify.append({"transaction_id": str(tid), "severity": sc["severity"],
                               "amount": None, "auto_blocked": False})

        if flag_account and fraud_cfg.get("flag_account_on_block"):
            fraud_config_service.flag_account(payload.user_id, "Auto-blocked fraudulent transaction")

        fraud_flagged = sum(1 for s in scored if s["is_fraud"])

        audit_logs_collection.insert_one({
            "action": "bulk_create_transactions",
            "actor_id": current_admin["id"],
            "actor_email": current_admin.get("email"),
            "target_user_id": payload.user_id,
            "details": {
                "count": len(ids), "fraud_flagged": fraud_flagged,
                "rejected": len(rejections), "source": source,
                "spend_total": round(spend_total, 2), "deposit_total": round(deposit_total, 2),
            },
            "created_at": now,
        })

        # attach amount to notifications by transaction id
        amt_by_id = {str(tid): td["Amount"] for tid, td in zip(ids, txn_docs)}
        for n in notify:
            n["amount"] = amt_by_id.get(n["transaction_id"], 0.0)

        return {
            "ids": [str(i) for i in ids], "errors": errors,
            "fraud_flagged": fraud_flagged, "notify": notify,
            "posted_count": posted_count, "deposit_total": round(deposit_total, 2),
            "spend_total": round(spend_total, 2), "rejections": rejections,
        }

    outcome = await run_in_threadpool(_process)

    if not outcome["ids"]:
        return BulkCreateResult(
            success=False, created_count=0,
            failed_count=len(outcome["errors"]), fraud_flagged=0,
            errors=outcome["errors"],
        )

    # Real-time fraud notification — ONE summary (not one per row) so a bulk
    # import never floods the notification center.
    notify = outcome["notify"]
    if notify:
        worst = "critical" if any(n["severity"] == "critical" for n in notify) else (
            "high" if any(n["severity"] == "high" for n in notify) else "medium")
        n_fraud = len(notify)
        total_amt = sum(float(n.get("amount") or 0) for n in notify)
        if n_fraud == 1:
            msg = f"A transaction of ${total_amt:,.2f} was flagged as fraudulent."
        else:
            msg = f"{n_fraud} transactions (${total_amt:,.2f}) were flagged as fraudulent."
        await notif_service.create_notification(
            audience=payload.user_id, user_id=payload.user_id, type="fraud_alert",
            title="Potential fraud detected", message=msg, severity=worst,
            transaction_id=notify[0]["transaction_id"],
        )
        await notif_service.create_notification(
            audience=ADMINS, user_id=None, type="fraud_alert",
            title=f"Fraud flagged ({worst})",
            message=f"{n_fraud} transaction(s) flagged for {target_username or payload.user_id}.",
            severity=worst, transaction_id=notify[0]["transaction_id"],
        )

    # Tell the affected user and all admins their data changed.
    await broker.publish_to_user(payload.user_id, "transactions_updated", {"reason": "bulk_create"})
    await broker.publish_to_admins(
        "transactions_updated",
        {"reason": "bulk_create", "user_id": payload.user_id, "count": len(outcome["ids"])},
    )

    return BulkCreateResult(
        success=True,
        created_count=len(outcome["ids"]),
        failed_count=len(outcome["errors"]),
        fraud_flagged=outcome["fraud_flagged"],
        errors=outcome["errors"],
        transaction_ids=outcome["ids"],
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

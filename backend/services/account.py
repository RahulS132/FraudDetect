"""Account / balance service.

Balance model (intuitive debit + credit hybrid):

    current_balance  = the user's spendable money (their account balance).
                       Admin "add funds" increases it; "remove funds" / spends
                       decrease it.
    credit_limit     = the user's credit ceiling (independent of the balance).
    credit_used      = how much of the credit line has been drawn.
    available_credit = credit_limit - credit_used   (0 when credit suspended).
    spending_power   = current_balance + available_credit  (what they can spend).
    credit_utilization = credit_used / credit_limit * 100.

A purchase is paid from the cash balance first; only the shortfall draws on the
credit line. So adding a balance increases what the user has and leaves the
credit line untouched (utilization stays at 0).

All admin balance/credit mutations go through here so every change is:
  * bounds-checked,
  * recorded in `account_events` (user-visible history + credit-limit history),
  * recorded in `audit_logs` (security trail) with before/after values.

Every function here is synchronous (pymongo is sync). Routes call them inside
`run_in_threadpool` so the event loop / SSE streams stay responsive.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from bson import ObjectId

from database import users_collection, account_events_collection, transactions_collection
from models import DEFAULT_CREDIT_LIMIT, AccountStatus
from services import audit


def _month_start() -> datetime:
    """First instant of the current UTC calendar month."""
    now = datetime.utcnow()
    return datetime(now.year, now.month, 1)


def monthly_spend(user_id: str) -> float:
    """Sum of this calendar month's approved transaction amounts for a user.

    Drives the (monthly-resetting) credit-utilization figure. Computed from
    transactions by `created_at`, so it resets automatically each month and
    increases as new transactions are added this month.
    """
    try:
        agg = list(transactions_collection.aggregate([
            {"$match": {"user_id": user_id, "is_approved": True,
                        "created_at": {"$gte": _month_start()}}},
            {"$group": {"_id": None, "total": {"$sum": "$Amount"}}},
        ]))
        return float(agg[0]["total"]) if agg else 0.0
    except Exception:
        return 0.0


def user_amount_stats(user_id: str) -> Dict[str, Any]:
    """Mean/std/count of an account's debit history + recent velocity.

    Feeds the per-account anomaly (z-score) and velocity signals of the fraud
    scorer. Only spends (is_approved or fraud debits) count toward the pattern.
    """
    try:
        from datetime import timedelta
        agg = list(transactions_collection.aggregate([
            {"$match": {"user_id": user_id, "Amount": {"$gt": 0}}},
            {"$group": {"_id": None, "mean": {"$avg": "$Amount"},
                        "std": {"$stdDevPop": "$Amount"}, "count": {"$sum": 1}}},
        ]))
        mean = float(agg[0]["mean"]) if agg and agg[0].get("mean") is not None else None
        std = float(agg[0]["std"]) if agg and agg[0].get("std") is not None else None
        count = int(agg[0]["count"]) if agg else 0
        recent = transactions_collection.count_documents({
            "user_id": user_id,
            "created_at": {"$gte": datetime.utcnow() - timedelta(hours=1)},
        })
        return {"mean": mean, "std": std, "count": count, "recent_count": int(recent)}
    except Exception:
        return {"mean": None, "std": None, "count": 0, "recent_count": 0}


def monthly_spend_map() -> Dict[str, float]:
    """{user_id: this-month approved spend} for all users, in one aggregation."""
    try:
        agg = transactions_collection.aggregate([
            {"$match": {"is_approved": True, "created_at": {"$gte": _month_start()}}},
            {"$group": {"_id": "$user_id", "total": {"$sum": "$Amount"}}},
        ])
        return {r["_id"]: float(r["total"]) for r in agg if r.get("_id")}
    except Exception:
        return {}


# ── helpers ──────────────────────────────────────────────────────────────────

def default_account() -> Dict[str, Any]:
    return {
        "credit_limit": DEFAULT_CREDIT_LIMIT,
        "current_balance": 0.0,
        "credit_used": 0.0,
        "total_spending": 0.0,
        "total_deposits": 0.0,
        "total_transactions": 0,
        "is_frozen": False,
        "credit_suspended": False,
        "currency": "USD",
        "updated_at": datetime.utcnow(),
    }


def _acct(user: Dict[str, Any]) -> Dict[str, Any]:
    """Return the account sub-document, filling defaults for legacy users."""
    base = default_account()
    base.update(user.get("account") or {})
    return base


def compute_summary(user: Dict[str, Any], month_spend: Optional[float] = None) -> Dict[str, Any]:
    """Build an AccountSummary-shaped dict from a user document.

    ``month_spend`` is this calendar month's approved spend; when provided it
    drives the **monthly-resetting** credit-utilization figure (uncapped, so it
    can read above 100% once the month's spend exceeds the limit). A credit
    limit of 0 means **no limit applied** — credit is effectively unlimited and
    utilization is reported as 0.
    """
    a = _acct(user)
    credit_limit = float(a.get("credit_limit", DEFAULT_CREDIT_LIMIT))
    current_balance = float(a.get("current_balance", 0.0))
    credit_used = float(a.get("credit_used", 0.0))
    credit_suspended = bool(a.get("credit_suspended", False))
    has_limit = credit_limit > 0
    month_spend = float(month_spend) if month_spend is not None else 0.0

    if not has_limit:
        # No credit limit applied → unlimited credit line.
        available_credit = 0.0
        utilization = 0.0
        spending_power = round(current_balance, 2)
    else:
        available_credit = 0.0 if credit_suspended else max(0.0, round(credit_limit - credit_used, 2))
        # Monthly utilization — NOT capped at 100% so it reflects over-limit spend.
        utilization = round(month_spend / credit_limit * 100, 2)
        spending_power = round(current_balance + available_credit, 2)

    return {
        "user_id": str(user["_id"]),
        "username": user.get("username"),
        "email": user.get("email"),
        "status": user.get("status", AccountStatus.ACTIVE.value),
        "credit_limit": round(credit_limit, 2),
        "has_credit_limit": has_limit,
        "current_balance": round(current_balance, 2),
        "credit_used": round(credit_used, 2),
        "available_credit": available_credit,
        "spending_power": spending_power,
        "credit_utilization": max(0.0, utilization),
        "monthly_spend": round(month_spend, 2),
        "total_spending": round(float(a.get("total_spending", 0.0)), 2),
        "total_deposits": round(float(a.get("total_deposits", 0.0)), 2),
        "total_transactions": int(a.get("total_transactions", 0)),
        "is_frozen": bool(a.get("is_frozen", False)),
        "credit_suspended": credit_suspended,
        "currency": a.get("currency", "USD"),
        "updated_at": a.get("updated_at"),
        "force_2fa": bool(user.get("force_2fa", False)),
        "email_verified": user.get("email_verified", True) is not False,
    }


def account_view(user: Dict[str, Any]) -> Dict[str, Any]:
    """compute_summary + this month's spend (for display endpoints)."""
    return compute_summary(user, monthly_spend(str(user["_id"])))


def _snapshot(a: Dict[str, Any]) -> Dict[str, Any]:
    credit_limit = float(a.get("credit_limit", DEFAULT_CREDIT_LIMIT))
    current_balance = float(a.get("current_balance", 0.0))
    credit_used = float(a.get("credit_used", 0.0))
    suspended = bool(a.get("credit_suspended", False))
    return {
        "credit_limit": round(credit_limit, 2),
        "current_balance": round(current_balance, 2),
        "credit_used": round(credit_used, 2),
        "available_credit": round(0.0 if suspended else max(0.0, credit_limit - credit_used), 2),
        "is_frozen": bool(a.get("is_frozen", False)),
        "credit_suspended": suspended,
    }


def _record_event(
    user_id: str,
    type_: str,
    before: Dict[str, Any],
    after: Dict[str, Any],
    actor_id: Optional[str],
    actor_email: Optional[str],
    amount: Optional[float] = None,
    note: Optional[str] = None,
) -> None:
    account_events_collection.insert_one(
        {
            "user_id": user_id,
            "type": type_,
            "amount": amount,
            "before": before,
            "after": after,
            "actor_id": actor_id,
            "actor_email": actor_email,
            "note": note,
            "created_at": datetime.utcnow(),
        }
    )


def _persist(user_oid: ObjectId, account: Dict[str, Any]) -> None:
    account["updated_at"] = datetime.utcnow()
    users_collection.update_one({"_id": user_oid}, {"$set": {"account": account}})


def get_user_or_raise(user_id: str) -> Dict[str, Any]:
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise ValueError("User not found")
    return user


# ── admin mutations ──────────────────────────────────────────────────────────

def add_funds(user_id: str, amount: float, actor: Dict[str, Any], note: Optional[str] = None) -> Dict[str, Any]:
    """Deposit money into the user's spendable balance."""
    user = get_user_or_raise(user_id)
    a = _acct(user)
    before = _snapshot(a)
    a["current_balance"] = round(float(a["current_balance"]) + amount, 2)
    a["total_deposits"] = round(float(a.get("total_deposits", 0.0)) + amount, 2)
    after = _snapshot(a)
    _persist(user["_id"], a)
    _record_event(user_id, "add_funds", before, after, actor.get("id"), actor.get("email"), amount, note)
    audit.record("balance_add_funds", actor.get("id"), actor.get("email"), user_id,
                 {"amount": amount, "before": before, "after": after, "note": note})
    return account_view(users_collection.find_one({"_id": user["_id"]}))


def remove_funds(user_id: str, amount: float, actor: Dict[str, Any], note: Optional[str] = None) -> Dict[str, Any]:
    """Withdraw money from the user's spendable balance (floored at 0)."""
    user = get_user_or_raise(user_id)
    a = _acct(user)
    before = _snapshot(a)
    a["current_balance"] = round(max(0.0, float(a["current_balance"]) - amount), 2)
    after = _snapshot(a)
    _persist(user["_id"], a)
    _record_event(user_id, "remove_funds", before, after, actor.get("id"), actor.get("email"), amount, note)
    audit.record("balance_remove_funds", actor.get("id"), actor.get("email"), user_id,
                 {"amount": amount, "before": before, "after": after, "note": note})
    return account_view(users_collection.find_one({"_id": user["_id"]}))


def set_balance(user_id: str, balance: float, actor: Dict[str, Any], note: Optional[str] = None) -> Dict[str, Any]:
    user = get_user_or_raise(user_id)
    a = _acct(user)
    before = _snapshot(a)
    a["current_balance"] = round(float(balance), 2)
    after = _snapshot(a)
    _persist(user["_id"], a)
    _record_event(user_id, "set_balance", before, after, actor.get("id"), actor.get("email"), balance, note)
    audit.record("balance_set", actor.get("id"), actor.get("email"), user_id,
                 {"before": before, "after": after, "note": note})
    return account_view(users_collection.find_one({"_id": user["_id"]}))


def set_credit_limit(user_id: str, *, credit_limit: Optional[float], delta: Optional[float],
                     actor: Dict[str, Any], note: Optional[str] = None) -> Dict[str, Any]:
    user = get_user_or_raise(user_id)
    a = _acct(user)
    before = _snapshot(a)
    if credit_limit is not None:
        new_limit = float(credit_limit)
    else:
        new_limit = float(a.get("credit_limit", DEFAULT_CREDIT_LIMIT)) + float(delta or 0.0)
    a["credit_limit"] = round(max(0.0, new_limit), 2)
    after = _snapshot(a)
    _persist(user["_id"], a)
    _record_event(user_id, "credit_limit_change", before, after, actor.get("id"), actor.get("email"), None, note)
    audit.record("credit_limit_change", actor.get("id"), actor.get("email"), user_id,
                 {"before": before, "after": after, "note": note})
    return account_view(users_collection.find_one({"_id": user["_id"]}))


def set_credit_suspended(user_id: str, suspended: bool, actor: Dict[str, Any], note: Optional[str] = None) -> Dict[str, Any]:
    user = get_user_or_raise(user_id)
    a = _acct(user)
    before = _snapshot(a)
    a["credit_suspended"] = bool(suspended)
    after = _snapshot(a)
    _persist(user["_id"], a)
    ev = "credit_suspend" if suspended else "credit_unsuspend"
    _record_event(user_id, ev, before, after, actor.get("id"), actor.get("email"), None, note)
    audit.record(ev, actor.get("id"), actor.get("email"), user_id,
                 {"before": before, "after": after, "note": note})
    return account_view(users_collection.find_one({"_id": user["_id"]}))


def set_frozen(user_id: str, frozen: bool, actor: Dict[str, Any], note: Optional[str] = None) -> Dict[str, Any]:
    user = get_user_or_raise(user_id)
    a = _acct(user)
    before = _snapshot(a)
    a["is_frozen"] = bool(frozen)
    after = _snapshot(a)
    _persist(user["_id"], a)
    ev = "freeze" if frozen else "unfreeze"
    _record_event(user_id, ev, before, after, actor.get("id"), actor.get("email"), None, note)
    audit.record("balance_" + ev, actor.get("id"), actor.get("email"), user_id,
                 {"before": before, "after": after, "note": note})
    return account_view(users_collection.find_one({"_id": user["_id"]}))


def reset_balance(user_id: str, actor: Dict[str, Any], note: Optional[str] = None) -> Dict[str, Any]:
    """Reset spendable balance and drawn credit to zero."""
    user = get_user_or_raise(user_id)
    a = _acct(user)
    before = _snapshot(a)
    a["current_balance"] = 0.0
    a["credit_used"] = 0.0
    after = _snapshot(a)
    _persist(user["_id"], a)
    _record_event(user_id, "reset", before, after, actor.get("id"), actor.get("email"), None, note)
    audit.record("balance_reset", actor.get("id"), actor.get("email"), user_id,
                 {"before": before, "after": after, "note": note})
    return account_view(users_collection.find_one({"_id": user["_id"]}))


# ── spend application (used by transaction creation pipeline) ─────────────────

class BalanceError(Exception):
    """Raised when a spend cannot be applied (frozen / over spending power)."""
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def check_can_spend(user: Dict[str, Any], amount: float) -> Tuple[bool, str, float]:
    """Return (ok, reason, spending_power) without mutating anything.

    A spend is allowed if the account isn't frozen and the amount fits within
    the cash balance plus available credit.
    """
    a = _acct(user)
    if bool(a.get("is_frozen", False)):
        return False, "Account balance is frozen", 0.0
    s = compute_summary(user)
    # No credit limit applied → unlimited credit; only a freeze can block.
    if not s["has_credit_limit"]:
        return True, "", float("inf")
    power = s["spending_power"]
    if amount > power:
        return False, (
            f"Transaction ${amount:,.2f} exceeds available funds "
            f"${power:,.2f} (balance ${s['current_balance']:,.2f} + credit ${s['available_credit']:,.2f})"
        ), power
    return True, "", power


def commit_batch(user_id: str, *, final_balance: float, final_credit_used: float,
                 spend_total: float = 0.0, deposit_total: float = 0.0,
                 count: int = 0) -> Dict[str, float]:
    """Persist a batch's money movements in one write.

    The caller (the transaction pipeline) has already walked the batch in order
    — debits draw cash then credit, deposits add cash back — and knows the exact
    resulting `final_balance` / `final_credit_used`. We set those authoritatively
    (avoids order-of-operations errors when a deposit and a purchase share a
    batch) and bump the lifetime spend/deposit/count totals.
    """
    user = get_user_or_raise(user_id)
    a = _acct(user)
    bal_before = round(float(a.get("current_balance", 0.0)), 2)
    a["current_balance"] = round(max(0.0, final_balance), 2)
    a["credit_used"] = round(max(0.0, final_credit_used), 2)
    a["total_spending"] = round(float(a.get("total_spending", 0.0)) + spend_total, 2)
    a["total_deposits"] = round(float(a.get("total_deposits", 0.0)) + deposit_total, 2)
    a["total_transactions"] = int(a.get("total_transactions", 0)) + count
    bal_after = a["current_balance"]
    _persist(user["_id"], a)
    if count:
        _record_event(
            user_id, "spend",
            {"current_balance": bal_before}, {"current_balance": bal_after},
            None, None, round(spend_total - deposit_total, 2), f"{count} transaction(s)",
        )
    return {"balance_before": bal_before, "balance_after": bal_after}


# ── history ──────────────────────────────────────────────────────────────────

def get_history(user_id: str, limit: int = 100) -> list:
    docs = (
        account_events_collection.find({"user_id": user_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    out = []
    for d in docs:
        out.append({
            "id": str(d["_id"]),
            "user_id": d.get("user_id"),
            "type": d.get("type"),
            "amount": d.get("amount"),
            "before": d.get("before"),
            "after": d.get("after"),
            "actor_id": d.get("actor_id"),
            "actor_email": d.get("actor_email"),
            "note": d.get("note"),
            "created_at": d.get("created_at"),
        })
    return out

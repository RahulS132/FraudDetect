"""Account / balance + user-blocking routes.

User endpoints (own account only):
    GET  /api/account/me
    GET  /api/account/me/history

Admin endpoints (any user):
    GET   /api/admin/users/{id}/account
    POST  /api/admin/users/{id}/account/add-funds
    POST  /api/admin/users/{id}/account/remove-funds
    PATCH /api/admin/users/{id}/account/balance
    PATCH /api/admin/users/{id}/account/credit-limit
    POST  /api/admin/users/{id}/account/credit-suspend
    POST  /api/admin/users/{id}/account/freeze
    POST  /api/admin/users/{id}/account/reset
    POST  /api/admin/users/{id}/block
    POST  /api/admin/users/{id}/unblock
    PATCH /api/admin/users/{id}/status
    GET   /api/admin/users/{id}/status-history
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from bson import ObjectId
from bson.errors import InvalidId

from models import (
    AccountSummary, AccountDetailResponse,
    AmountRequest, SetBalanceRequest, CreditLimitRequest, ToggleRequest,
    BlockRequest, UnblockRequest, StatusRequest,
    Toggle2FARequest, LoginAttemptResponse,
)
from database import users_collection
from auth import get_current_user, get_current_admin
from services import account as account_service
from services import blocking as blocking_service
from services import security_log
from services import audit

user_router = APIRouter(prefix="/api/account", tags=["Account"])
admin_router = APIRouter(prefix="/api/admin", tags=["Admin - Accounts"])


def _oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid id format")


# ── user: own account ────────────────────────────────────────────────────────

@user_router.get("/me", response_model=AccountSummary)
async def my_account(current_user: dict = Depends(get_current_user)):
    def _work():
        user = users_collection.find_one({"_id": ObjectId(current_user["id"])})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return account_service.compute_summary(user)
    return await run_in_threadpool(_work)


@user_router.get("/me/history")
async def my_account_history(
    current_user: dict = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
):
    return await run_in_threadpool(account_service.get_history, current_user["id"], limit)


# ── admin: view + mutate any account ─────────────────────────────────────────

@admin_router.get("/users/{user_id}/account", response_model=AccountDetailResponse)
async def admin_get_account(user_id: str, current_admin: dict = Depends(get_current_admin)):
    _oid(user_id)

    def _work():
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return {
            "account": account_service.compute_summary(user),
            "history": account_service.get_history(user_id, 100),
        }
    return await run_in_threadpool(_work)


def _wrap(fn, *args):
    """Run a sync account-service call in the threadpool, mapping ValueError→404."""
    async def runner():
        try:
            return await run_in_threadpool(fn, *args)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    return runner()


@admin_router.post("/users/{user_id}/account/add-funds", response_model=AccountSummary)
async def admin_add_funds(user_id: str, body: AmountRequest, current_admin: dict = Depends(get_current_admin)):
    _oid(user_id)
    return await _wrap(account_service.add_funds, user_id, body.amount, current_admin, body.note)


@admin_router.post("/users/{user_id}/account/remove-funds", response_model=AccountSummary)
async def admin_remove_funds(user_id: str, body: AmountRequest, current_admin: dict = Depends(get_current_admin)):
    _oid(user_id)
    return await _wrap(account_service.remove_funds, user_id, body.amount, current_admin, body.note)


@admin_router.patch("/users/{user_id}/account/balance", response_model=AccountSummary)
async def admin_set_balance(user_id: str, body: SetBalanceRequest, current_admin: dict = Depends(get_current_admin)):
    _oid(user_id)
    return await _wrap(account_service.set_balance, user_id, body.balance, current_admin, body.note)


@admin_router.patch("/users/{user_id}/account/credit-limit", response_model=AccountSummary)
async def admin_set_credit_limit(user_id: str, body: CreditLimitRequest, current_admin: dict = Depends(get_current_admin)):
    _oid(user_id)

    async def runner():
        try:
            return await run_in_threadpool(
                lambda: account_service.set_credit_limit(
                    user_id, credit_limit=body.credit_limit, delta=body.delta,
                    actor=current_admin, note=body.note,
                )
            )
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    return await runner()


@admin_router.post("/users/{user_id}/account/credit-suspend", response_model=AccountSummary)
async def admin_credit_suspend(user_id: str, body: ToggleRequest, current_admin: dict = Depends(get_current_admin)):
    _oid(user_id)
    return await _wrap(account_service.set_credit_suspended, user_id, body.enabled, current_admin, body.note)


@admin_router.post("/users/{user_id}/account/freeze", response_model=AccountSummary)
async def admin_freeze(user_id: str, body: ToggleRequest, current_admin: dict = Depends(get_current_admin)):
    _oid(user_id)
    return await _wrap(account_service.set_frozen, user_id, body.enabled, current_admin, body.note)


@admin_router.post("/users/{user_id}/account/reset", response_model=AccountSummary)
async def admin_reset(user_id: str, current_admin: dict = Depends(get_current_admin)):
    _oid(user_id)
    return await _wrap(account_service.reset_balance, user_id, current_admin, None)


# ── admin: blocking / status ─────────────────────────────────────────────────

@admin_router.post("/users/{user_id}/block")
async def admin_block(user_id: str, body: BlockRequest, current_admin: dict = Depends(get_current_admin)):
    _oid(user_id)
    if user_id == current_admin.get("id"):
        raise HTTPException(status_code=400, detail="You cannot block your own account")

    async def runner():
        try:
            return await run_in_threadpool(
                lambda: blocking_service.block_user(
                    user_id, reason_code=body.reason_code.value,
                    reason=body.reason, notes=body.notes, actor=current_admin,
                )
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return await runner()


@admin_router.post("/users/{user_id}/unblock")
async def admin_unblock(user_id: str, body: UnblockRequest, current_admin: dict = Depends(get_current_admin)):
    _oid(user_id)

    async def runner():
        try:
            return await run_in_threadpool(
                lambda: blocking_service.unblock_user(user_id, notes=body.notes, actor=current_admin)
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return await runner()


@admin_router.patch("/users/{user_id}/status")
async def admin_set_status(user_id: str, body: StatusRequest, current_admin: dict = Depends(get_current_admin)):
    _oid(user_id)
    if user_id == current_admin.get("id"):
        raise HTTPException(status_code=400, detail="You cannot change your own status")

    async def runner():
        try:
            return await run_in_threadpool(
                lambda: blocking_service.set_status(
                    user_id, status=body.status.value, notes=body.notes, actor=current_admin
                )
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return await runner()


@admin_router.get("/users/{user_id}/status-history")
async def admin_status_history(
    user_id: str, current_admin: dict = Depends(get_current_admin),
    limit: int = Query(100, ge=1, le=500),
):
    _oid(user_id)
    return await run_in_threadpool(blocking_service.get_history, user_id, limit)


# ── admin: 2FA + login history ───────────────────────────────────────────────

@admin_router.patch("/users/{user_id}/2fa")
async def admin_toggle_2fa(user_id: str, body: Toggle2FARequest, current_admin: dict = Depends(get_current_admin)):
    oid = _oid(user_id)

    def _work():
        res = users_collection.update_one({"_id": oid}, {"$set": {"force_2fa": body.enabled}})
        if res.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        audit.record(
            "2fa_forced" if body.enabled else "2fa_disabled",
            current_admin.get("id"), current_admin.get("email"), user_id,
            {"force_2fa": body.enabled},
        )
        return {"force_2fa": body.enabled}
    return await run_in_threadpool(_work)


@admin_router.get("/users/{user_id}/login-history", response_model=list[LoginAttemptResponse])
async def admin_login_history(
    user_id: str, current_admin: dict = Depends(get_current_admin),
    limit: int = Query(50, ge=1, le=200),
):
    _oid(user_id)

    def _work():
        user = users_collection.find_one({"_id": ObjectId(user_id)}, {"email": 1})
        email = user.get("email") if user else None
        return security_log.list_for_user(user_id, email, limit)
    return await run_in_threadpool(_work)

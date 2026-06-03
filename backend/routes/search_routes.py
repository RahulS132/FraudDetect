"""Transaction search, detail, and tag-update routes.

Scope rules:
    • A normal user may only search / view / edit their own transactions.
    • An admin may search across all transactions and view/edit any.

Endpoints:
    GET   /api/transactions/search          paginated search (auto-scoped)
    GET   /api/transactions/{txn_id}        full transaction detail
    PATCH /api/transactions/{txn_id}/tags   update tag/category/description
    GET   /api/transactions/tags/options    available tag labels
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from bson import ObjectId

from models import TransactionListResponse, TransactionDetail, TagUpdate, TransactionTag, UserRole
from database import transactions_collection
from auth import get_current_user
from services.search import query_transactions, get_transaction_detail
from services import audit
from services.events import broker

router = APIRouter(prefix="/api/transactions", tags=["Transactions - Search"])


def _is_admin(user: dict) -> bool:
    return user.get("role") == UserRole.ADMIN.value


@router.get("/search", response_model=TransactionListResponse)
async def search_transactions(
    current_user: dict = Depends(get_current_user),
    q: Optional[str] = Query(None, description="Free-text across id, user, category, description, tag, amount"),
    tag: Optional[str] = None,
    category: Optional[str] = None,
    fraud_status: Optional[str] = Query(None, regex="^(fraud|approved)$"),
    creation_source: Optional[str] = Query(None, regex="^(csv_upload|admin_manual|admin_bulk)$"),
    min_amount: Optional[float] = Query(None, ge=0),
    max_amount: Optional[float] = Query(None, ge=0),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort_by: str = Query("created_at", regex="^(created_at|amount|fraud_score)$"),
    sort_dir: str = Query("desc", regex="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
):
    """Search transactions. Admins search globally; users are scoped to self."""
    scope = None if _is_admin(current_user) else current_user["id"]
    return await run_in_threadpool(
        query_transactions,
        scope_user_id=scope,
        q=q,
        tag=tag,
        category=category,
        fraud_status=fraud_status,
        creation_source=creation_source,
        min_amount=min_amount,
        max_amount=max_amount,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )


@router.get("/tags/options")
async def tag_options(current_user: dict = Depends(get_current_user)):
    """Return the canonical tag list for pickers/filters."""
    return {"tags": [t.value for t in TransactionTag]}


@router.get("/{txn_id}", response_model=TransactionDetail)
async def transaction_detail(
    txn_id: str, current_user: dict = Depends(get_current_user)
):
    detail = await run_in_threadpool(
        get_transaction_detail,
        transaction_id=txn_id,
        requester_user_id=current_user["id"],
        is_admin=_is_admin(current_user),
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return detail


@router.patch("/{txn_id}/tags", response_model=TransactionDetail)
async def update_transaction_tags(
    txn_id: str,
    update: TagUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update tag / category / description on an existing transaction.

    Users may only edit their own; admins may edit any (and the edit is audited
    when it targets another user's data)."""
    try:
        oid = ObjectId(txn_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid transaction id")

    is_admin = _is_admin(current_user)

    def _load():
        return transactions_collection.find_one({"_id": oid})

    txn = await run_in_threadpool(_load)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if not is_admin and txn.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Not allowed to edit this transaction")

    set_fields = {}
    if update.merchant is not None:
        set_fields["merchant"] = update.merchant
    if update.tag is not None:
        set_fields["tag"] = update.tag.value
    if update.category is not None:
        set_fields["category"] = update.category
    if update.description is not None:
        set_fields["description"] = update.description
    if not set_fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_fields["updated_at"] = datetime.utcnow()

    await run_in_threadpool(
        lambda: transactions_collection.update_one({"_id": oid}, {"$set": set_fields})
    )

    # Audit when an admin edits someone else's transaction.
    if is_admin and txn.get("user_id") != current_user["id"]:
        await run_in_threadpool(
            audit.record,
            "update_transaction_tags",
            current_user["id"],
            current_user.get("email"),
            txn.get("user_id"),
            {"transaction_id": txn_id, "changes": {k: v for k, v in set_fields.items() if k != "updated_at"}},
        )

    # Notify the owner's tabs that their data changed.
    owner = txn.get("user_id")
    if owner:
        await broker.publish_to_user(owner, "transactions_updated", {"reason": "tag_update"})

    detail = await run_in_threadpool(
        get_transaction_detail,
        transaction_id=txn_id,
        requester_user_id=current_user["id"],
        is_admin=is_admin,
    )
    return detail

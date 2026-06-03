"""Shared transaction search / listing service.

Builds a single aggregation that joins ``transactions`` with
``detection_results`` (and ``users`` for name/email), applies free-text and
structured filters, sorts, and paginates. Used by:

    • user-scoped search      (a user searches their own transactions)
    • admin global search     (search across all transactions)
    • admin per-user listing  (transactions for one selected user)

Returned shape matches ``models.TransactionListResponse``.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from bson import ObjectId

from database import transactions_collection
from fraud_detection import severity_from_score


def _build_detail(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Map an aggregation/transaction row into a TransactionDetail-shaped dict.

    Fraud fields are read from the transaction document itself (denormalized),
    falling back to a joined ``det`` sub-document if present (used by the
    single-transaction detail endpoint, and for any rows not yet backfilled).
    """
    det = doc.get("det") or {}
    user = doc.get("user") or {}

    # Prefer denormalized fields on the transaction; fall back to joined det.
    anomaly = doc.get("anomaly_score", det.get("anomaly_score"))
    is_fraud = doc.get("is_fraud", det.get("is_fraud"))
    is_approved = doc.get("is_approved", det.get("is_approved"))
    actual_class = doc.get("actual_class", det.get("actual_class"))
    severity = doc.get("severity", det.get("severity"))
    if severity is None and anomaly is not None:
        severity = severity_from_score(anomaly, bool(is_fraud))

    # Known business fields are surfaced explicitly; everything else (the PCA
    # V1–V28 features, Time, etc.) is bundled into `metadata`.
    known = {
        "_id", "user_id", "Amount", "Class", "merchant", "category", "tag",
        "description", "creation_source", "created_by", "transaction_time",
        "created_at", "_id_str", "det", "user",
        "is_fraud", "is_approved", "anomaly_score", "severity", "actual_class",
    }
    metadata = {
        k: v for k, v in doc.items()
        if k not in known and not k.startswith("V") and k != "Time"
    }
    # Keep a couple of useful raw signals in metadata.
    if "Time" in doc:
        metadata["time_offset"] = doc.get("Time")
    if actual_class is not None:
        metadata["actual_class"] = actual_class

    return {
        "transaction_id": str(doc["_id"]),
        "user_id": doc.get("user_id"),
        "username": user.get("username"),
        "user_email": user.get("email"),
        "amount": float(doc.get("Amount", 0.0)),
        "transaction_time": doc.get("transaction_time") or doc.get("created_at"),
        "created_at": doc.get("created_at"),
        "merchant": doc.get("merchant"),
        "category": doc.get("category"),
        "tag": doc.get("tag"),
        "description": doc.get("description"),
        "fraud_score": anomaly,
        "fraud_severity": severity,
        "is_fraud": is_fraud,
        "is_approved": is_approved,
        "fraud_status": ("Fraud" if is_fraud else "Approved") if is_fraud is not None else None,
        "creation_source": doc.get("creation_source", "csv_upload"),
        "actual_class": actual_class,
        "metadata": metadata,
    }


def query_transactions(
    *,
    scope_user_id: Optional[str] = None,
    q: Optional[str] = None,
    tag: Optional[str] = None,
    category: Optional[str] = None,
    fraud_status: Optional[str] = None,        # "fraud" | "approved"
    creation_source: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    date_from: Optional[str] = None,           # ISO date (YYYY-MM-DD)
    date_to: Optional[str] = None,
    sort_by: str = "created_at",               # created_at | amount | fraud_score
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> Dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(200, page_size))

    # ────────────────────────────────────────────────────────────────────────
    # All filtering/sorting/pagination runs against the `transactions`
    # collection ALONE, using fields denormalized onto each transaction
    # (is_fraud, anomaly_score, severity). This keeps the query on indexed
    # fields and avoids joining the entire collection to detection_results on
    # every search — the old approach timed out on large datasets (Atlas M0).
    # We only join the `users` collection for the <=page_size rows we return.
    # ────────────────────────────────────────────────────────────────────────
    match: Dict[str, Any] = {}
    if scope_user_id:
        match["user_id"] = scope_user_id
    if tag:
        match["tag"] = tag
    if category:
        match["category"] = {"$regex": re.escape(category), "$options": "i"}
    if creation_source:
        match["creation_source"] = creation_source
    if fraud_status == "fraud":
        match["is_fraud"] = True
    elif fraud_status == "approved":
        match["is_fraud"] = False
    if min_amount is not None or max_amount is not None:
        amount_range: Dict[str, Any] = {}
        if min_amount is not None:
            amount_range["$gte"] = float(min_amount)
        if max_amount is not None:
            amount_range["$lte"] = float(max_amount)
        match["Amount"] = amount_range
    if date_from or date_to:
        date_range: Dict[str, Any] = {}
        try:
            if date_from:
                date_range["$gte"] = datetime.fromisoformat(date_from)
            if date_to:
                end = datetime.fromisoformat(date_to)
                date_range["$lte"] = end.replace(hour=23, minute=59, second=59)
        except ValueError:
            pass
        if date_range:
            match["created_at"] = date_range

    # Free-text search across denormalized text fields (no user join needed —
    # user matches are handled separately below to keep this index-friendly).
    if q:
        q_clean = q.strip()
        if q_clean:
            whole_or: List[Dict[str, Any]] = [{"user_id": q_clean}]
            # exact transaction id
            try:
                whole_or.append({"_id": ObjectId(q_clean)})
            except Exception:
                pass
            try:
                whole_or.append({"Amount": float(q_clean)})
            except ValueError:
                pass

            text_fields = ["merchant", "description", "category", "tag", "creation_source"]
            tokens = [t for t in re.split(r"\s+", q_clean) if t]
            token_and: List[Dict[str, Any]] = []
            for tok in tokens:
                tok_regex = {"$regex": re.escape(tok), "$options": "i"}
                token_and.append({"$or": [{f: tok_regex} for f in text_fields]})

            # Also let the query match a user's name/email (admin global search):
            # resolve matching user_ids up front (users is a tiny collection).
            if not scope_user_id:
                from database import users_collection
                u_regex = {"$regex": re.escape(q_clean), "$options": "i"}
                matched_users = users_collection.find(
                    {"$or": [{"username": u_regex}, {"email": u_regex}, {"full_name": u_regex}]},
                    {"_id": 1},
                )
                uid_list = [str(u["_id"]) for u in matched_users]
                if uid_list:
                    whole_or.append({"user_id": {"$in": uid_list}})

            combined: List[Dict[str, Any]] = list(whole_or)
            if token_and:
                combined.append({"$and": token_and} if len(token_and) > 1 else token_and[0])

            match["$or"] = combined

    sort_field = {
        "created_at": "created_at",
        "amount": "Amount",
        "fraud_score": "anomaly_score",
    }.get(sort_by, "created_at")
    direction = 1 if sort_dir == "asc" else -1

    # Count + page in one round trip. The $sort/$skip/$limit happen on indexed
    # transaction fields; only the page is materialised.
    pipeline: List[Dict[str, Any]] = [
        {"$match": match},
        {
            "$facet": {
                "meta": [{"$count": "total"}],
                "data": [
                    {"$sort": {sort_field: direction, "_id": direction}},
                    {"$skip": (page - 1) * page_size},
                    {"$limit": page_size},
                ],
            }
        },
    ]

    result = list(transactions_collection.aggregate(pipeline, allowDiskUse=True))
    if not result:
        return {
            "items": [], "total": 0, "page": page,
            "page_size": page_size, "total_pages": 0,
        }

    facet = result[0]
    total = facet["meta"][0]["total"] if facet["meta"] else 0
    page_docs = facet["data"]

    # Join users for just this page (fetch the distinct user_ids in one query).
    if page_docs:
        from database import users_collection
        uid_strs = {d.get("user_id") for d in page_docs if d.get("user_id")}
        oids = []
        for s in uid_strs:
            try:
                oids.append(ObjectId(s))
            except Exception:
                pass
        umap = {
            str(u["_id"]): u
            for u in users_collection.find(
                {"_id": {"$in": oids}}, {"username": 1, "email": 1, "full_name": 1}
            )
        }
        for d in page_docs:
            d["user"] = umap.get(d.get("user_id"), {})

    items = [_build_detail(d) for d in page_docs]
    total_pages = (total + page_size - 1) // page_size

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def get_transaction_detail(
    *, transaction_id: str, requester_user_id: str, is_admin: bool
) -> Optional[Dict[str, Any]]:
    """Fetch one transaction's full detail, enforcing ownership for non-admins."""
    try:
        oid = ObjectId(transaction_id)
    except Exception:
        return None

    match: Dict[str, Any] = {"_id": oid}
    if not is_admin:
        match["user_id"] = requester_user_id

    pipeline = [
        {"$match": match},
        {"$addFields": {"_id_str": {"$toString": "$_id"}}},
        {
            "$lookup": {
                "from": "detection_results",
                "localField": "_id_str",
                "foreignField": "transaction_id",
                "as": "det",
            }
        },
        {"$unwind": {"path": "$det", "preserveNullAndEmptyArrays": True}},
        {
            "$lookup": {
                "from": "users",
                "let": {"uid": "$user_id"},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": [{"$toString": "$_id"}, "$$uid"]}}},
                    {"$project": {"username": 1, "email": 1, "full_name": 1}},
                ],
                "as": "user",
            }
        },
        {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
    ]
    rows = list(transactions_collection.aggregate(pipeline))
    if not rows:
        return None
    return _build_detail(rows[0])

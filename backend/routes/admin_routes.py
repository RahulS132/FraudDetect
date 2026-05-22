from fastapi import APIRouter, Depends
from typing import List
from bson import ObjectId
import numpy as np
from models import AdminStats, UserFraudRate
from database import users_collection, transactions_collection, detection_results_collection
from auth import get_current_admin

router = APIRouter(prefix="/api/admin", tags=["Admin"])

@router.get("/analytics", response_model=AdminStats)
async def get_admin_analytics(current_admin: dict = Depends(get_current_admin)):
    """Get global analytics across all users (admin only)"""

    total_users = users_collection.count_documents({})

    pipeline = [
        {
            "$group": {
                "_id": None,
                "total_transactions": {"$sum": 1},
                "total_fraud_detected": {
                    "$sum": {"$cond": [{"$eq": ["$is_fraud", True]}, 1, 0]}
                },
                "approved_transactions": {
                    "$sum": {"$cond": [{"$eq": ["$is_approved", True]}, 1, 0]}
                },
                "rejected_transactions": {
                    "$sum": {"$cond": [{"$eq": ["$is_approved", False]}, 1, 0]}
                }
            }
        }
    ]

    result = list(detection_results_collection.aggregate(pipeline))

    if not result:
        return AdminStats(
            total_users=total_users, total_transactions=0,
            total_fraud_detected=0, global_fraud_rate=0.0,
            global_approval_rate=0.0, approved_transactions=0, rejected_transactions=0
        )

    stats = result[0]
    total_transactions = stats['total_transactions']
    total_fraud = stats['total_fraud_detected']
    approved    = stats['approved_transactions']

    return AdminStats(
        total_users=total_users,
        total_transactions=total_transactions,
        total_fraud_detected=total_fraud,
        global_fraud_rate=(total_fraud / total_transactions * 100) if total_transactions > 0 else 0.0,
        global_approval_rate=(approved / total_transactions * 100) if total_transactions > 0 else 0.0,
        approved_transactions=approved,
        rejected_transactions=stats['rejected_transactions']
    )


@router.get("/fraud-rates-by-user", response_model=List[UserFraudRate])
async def get_fraud_rates_by_user(current_admin: dict = Depends(get_current_admin)):
    """Get fraud rate breakdown by user (admin only)"""

    pipeline = [
        {
            "$group": {
                "_id": "$user_id",
                "total_transactions": {"$sum": 1},
                "fraud_count": {
                    "$sum": {"$cond": [{"$eq": ["$is_fraud", True]}, 1, 0]}
                }
            }
        },
        {
            "$lookup": {
                "from": "users",
                "let": {"user_id_str": "$_id"},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": [{"$toString": "$_id"}, "$$user_id_str"]}}}
                ],
                "as": "user_info"
            }
        },
        {"$unwind": "$user_info"},
        {
            "$project": {
                "user_id": "$_id",
                "username": "$user_info.username",
                "email": "$user_info.email",
                "total_transactions": 1,
                "fraud_count": 1,
                "fraud_rate": {
                    "$multiply": [
                        {"$divide": ["$fraud_count", "$total_transactions"]},
                        100
                    ]
                }
            }
        },
        {"$sort": {"fraud_rate": -1}}
    ]

    results = list(detection_results_collection.aggregate(pipeline))
    return [
        UserFraudRate(
            user_id=r['user_id'], username=r['username'], email=r['email'],
            total_transactions=r['total_transactions'], fraud_count=r['fraud_count'],
            fraud_rate=r['fraud_rate']
        )
        for r in results
    ]


# ── Global Anomaly Score Distribution ────────────────────────────────────────
# Sampled — no need to load every document for a histogram shape.

@router.get("/global-anomaly-distribution")
async def get_global_anomaly_distribution(current_admin: dict = Depends(get_current_admin)):
    """Histogram of anomaly_score across ALL users (sampled), split by fraud/legit."""

    docs = list(detection_results_collection.aggregate([
        {"$sample": {"size": 10000}},
        {"$project": {"anomaly_score": 1, "is_fraud": 1, "_id": 0}}
    ]))

    if not docs:
        return {"bins": [], "fraud_counts": [], "legit_counts": []}

    all_scores = np.array([d["anomaly_score"] for d in docs])
    is_fraud   = np.array([d["is_fraud"]      for d in docs], dtype=bool)

    mn, mx = float(all_scores.min()), float(all_scores.max())
    if mn == mx:
        return {"bins": [f"{mn:.3f}"],
                "fraud_counts": [int(is_fraud.sum())],
                "legit_counts": [int((~is_fraud).sum())]}

    bin_edges = np.linspace(mn, mx, 21)
    fraud_hist, _ = np.histogram(all_scores[is_fraud],  bins=bin_edges)
    legit_hist, _ = np.histogram(all_scores[~is_fraud], bins=bin_edges)

    return {
        "bins":         [f"{b:.3f}" for b in bin_edges[:-1]],
        "fraud_counts": fraud_hist.tolist(),
        "legit_counts": legit_hist.tolist()
    }


# ── Fraud Rate Trend Over Time ────────────────────────────────────────────────

@router.get("/fraud-rate-trend")
async def get_fraud_rate_trend(current_admin: dict = Depends(get_current_admin)):
    """Daily fraud counts and fraud-rate % across all users."""

    pipeline = [
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "total": {"$sum": 1},
                "fraud": {"$sum": {"$cond": [{"$eq": ["$is_fraud", True]}, 1, 0]}}
            }
        },
        {"$sort": {"_id": 1}}
    ]

    results = list(detection_results_collection.aggregate(pipeline))
    return {
        "dates":        [r["_id"]   for r in results],
        "total_counts": [r["total"] for r in results],
        "fraud_counts": [r["fraud"] for r in results],
        "fraud_rates":  [
            round(r["fraud"] / r["total"] * 100, 2) if r["total"] > 0 else 0.0
            for r in results
        ]
    }


# ── V-Feature Box Plots ───────────────────────────────────────────────────────
# Old approach: $lookup with $toObjectId per document — full collection scan.
# New approach: sample detection_results, fetch transactions with $in (indexed).

@router.get("/v-feature-boxplots")
async def get_v_feature_boxplots(current_admin: dict = Depends(get_current_admin)):
    """IQR stats for V1–V28 split by fraud vs legit."""

    v_fields = [f"V{i}" for i in range(1, 29)]

    def _fetch_and_join(match_filter: dict, limit: int) -> list:
        """Sample detection_results, join to transactions via indexed $in."""
        det_docs = list(detection_results_collection.aggregate([
            {"$match": match_filter},
            {"$limit": limit},
            {"$project": {"transaction_id": 1, "is_fraud": 1, "_id": 0}}
        ]))
        if not det_docs:
            return []

        txn_ids = [ObjectId(d["transaction_id"]) for d in det_docs if d.get("transaction_id")]
        proj    = {f: 1 for f in v_fields}
        txn_map = {
            str(doc["_id"]): doc
            for doc in transactions_collection.find({"_id": {"$in": txn_ids}}, proj)
        }

        merged = []
        for d in det_docs:
            txn = txn_map.get(d.get("transaction_id"))
            if txn:
                row = {"is_fraud": d["is_fraud"]}
                row.update({f: txn[f] for f in v_fields if f in txn})
                merged.append(row)
        return merged

    fraud_docs = _fetch_and_join({"is_fraud": True},  3000)
    legit_docs = _fetch_and_join({"is_fraud": False}, 3000)

    if not fraud_docs and not legit_docs:
        return {"features": [], "fraud": [], "legit": []}

    def boxplot_stats(docs, field):
        vals = [d[field] for d in docs if field in d and d[field] is not None]
        if not vals:
            return {"min": 0, "q1": 0, "median": 0, "q3": 0, "max": 0}
        arr = np.array(vals)
        return {
            "min":    float(np.min(arr)),
            "q1":     float(np.percentile(arr, 25)),
            "median": float(np.percentile(arr, 50)),
            "q3":     float(np.percentile(arr, 75)),
            "max":    float(np.max(arr))
        }

    return {
        "features": v_fields,
        "fraud":    [boxplot_stats(fraud_docs, f) for f in v_fields],
        "legit":    [boxplot_stats(legit_docs, f) for f in v_fields]
    }


# ── Confusion Matrix ──────────────────────────────────────────────────────────

@router.get("/confusion-matrix")
async def get_confusion_matrix(current_admin: dict = Depends(get_current_admin)):
    """actual_class vs is_fraud across all detection results."""

    pipeline = [
        {
            "$group": {
                "_id": {"actual_class": "$actual_class", "is_fraud": "$is_fraud"},
                "count": {"$sum": 1}
            }
        }
    ]

    results = list(detection_results_collection.aggregate(pipeline))
    matrix  = {"true_positive": 0, "false_positive": 0, "true_negative": 0, "false_negative": 0}

    for r in results:
        actual          = r["_id"]["actual_class"]
        predicted_fraud = r["_id"]["is_fraud"]
        count           = r["count"]
        if   actual == 1 and predicted_fraud:     matrix["true_positive"]  += count
        elif actual == 0 and predicted_fraud:     matrix["false_positive"] += count
        elif actual == 1 and not predicted_fraud: matrix["false_negative"] += count
        else:                                     matrix["true_negative"]  += count

    total = sum(matrix.values())
    tp, fp, fn, tn = (matrix["true_positive"], matrix["false_positive"],
                      matrix["false_negative"], matrix["true_negative"])

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    accuracy  = (tp + tn) / total if total > 0 else 0.0

    return {
        **matrix,
        "accuracy":  round(accuracy  * 100, 2),
        "precision": round(precision * 100, 2),
        "recall":    round(recall    * 100, 2),
        "f1_score":  round(f1        * 100, 2)
    }


# ── Amount Distribution by Class ─────────────────────────────────────────────
# Old approach: $lookup with $toObjectId — same full-scan problem as v-features.
# New approach: two-step $in join.

@router.get("/amount-distribution")
async def get_amount_distribution(current_admin: dict = Depends(get_current_admin)):
    """Overlapping histograms of transaction Amount for fraud vs legit."""

    def _fetch_amounts(match_filter: dict, limit: int) -> np.ndarray:
        det_docs = list(detection_results_collection.aggregate([
            {"$match": match_filter},
            {"$limit": limit},
            {"$project": {"transaction_id": 1, "_id": 0}}
        ]))
        if not det_docs:
            return np.array([])

        txn_ids = [ObjectId(d["transaction_id"]) for d in det_docs if d.get("transaction_id")]
        amounts = [
            doc["Amount"]
            for doc in transactions_collection.find({"_id": {"$in": txn_ids}}, {"Amount": 1})
            if "Amount" in doc
        ]
        return np.array(amounts)

    fraud_amounts = _fetch_amounts({"is_fraud": True},  3000)
    legit_amounts = _fetch_amounts({"is_fraud": False}, 3000)

    if len(fraud_amounts) == 0 and len(legit_amounts) == 0:
        return {"bins": [], "fraud_counts": [], "legit_counts": []}

    all_amounts = np.concatenate([a for a in [fraud_amounts, legit_amounts] if len(a) > 0])
    cap         = float(np.percentile(all_amounts, 99))
    bin_edges   = np.linspace(0, cap, 21)

    def hist(arr):
        if len(arr) == 0:
            return np.zeros(20, dtype=int)
        return np.histogram(arr[arr <= cap], bins=bin_edges)[0]

    bin_labels = [f"${bin_edges[i]:.0f}–${bin_edges[i+1]:.0f}" for i in range(len(bin_edges) - 1)]

    return {
        "bins":         bin_labels,
        "fraud_counts": hist(fraud_amounts).tolist(),
        "legit_counts": hist(legit_amounts).tolist()
    }

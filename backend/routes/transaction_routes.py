from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from typing import List
from datetime import datetime
from bson import ObjectId
import asyncio
import numpy as np
from models import DashboardStats
from database import transactions_collection, detection_results_collection
from auth import get_current_user
from fraud_detection import detector

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])

# ── Sync helper — runs in a thread pool so it never blocks the event loop ────

def _process_upload_sync(content: bytes, user_id: str) -> dict:
    """
    All CPU-bound work (pandas, Isolation Forest, MongoDB inserts) lives here.
    FastAPI's run_in_executor keeps the event loop free so other requests
    (login, dashboard, etc.) continue to work during a long upload.
    """
    original_df, results_df = detector.process_csv(content)
    uploaded_at = datetime.utcnow()

    transactions_to_insert = []
    detection_results_to_insert = []

    for idx, row in results_df.iterrows():
        transaction_doc = {
            "user_id": user_id,
            "Time": float(row['Time']),
            "V1": float(row['V1']),
            "V2": float(row['V2']),
            "V3": float(row['V3']),
            "V4": float(row['V4']),
            "V5": float(row['V5']),
            "V6": float(row['V6']),
            "V7": float(row['V7']),
            "V8": float(row['V8']),
            "V9": float(row['V9']),
            "V10": float(row['V10']),
            "V11": float(row['V11']),
            "V12": float(row['V12']),
            "V13": float(row['V13']),
            "V14": float(row['V14']),
            "V15": float(row['V15']),
            "V16": float(row['V16']),
            "V17": float(row['V17']),
            "V18": float(row['V18']),
            "V19": float(row['V19']),
            "V20": float(row['V20']),
            "V21": float(row['V21']),
            "V22": float(row['V22']),
            "V23": float(row['V23']),
            "V24": float(row['V24']),
            "V25": float(row['V25']),
            "V26": float(row['V26']),
            "V27": float(row['V27']),
            "V28": float(row['V28']),
            "Amount": float(row['Amount']),
            "Class": int(row['Class']),
            "created_at": uploaded_at
        }
        transactions_to_insert.append(transaction_doc)

    # Bulk insert transactions
    transaction_results = transactions_collection.insert_many(transactions_to_insert)
    transaction_ids = transaction_results.inserted_ids

    # Build detection results
    for (_, row_data), transaction_id in zip(results_df.iterrows(), transaction_ids):
        detection_doc = {
            "transaction_id": str(transaction_id),
            "user_id": user_id,
            "is_fraud": bool(row_data['is_fraud']),
            "is_approved": bool(row_data['is_approved']),
            "anomaly_score": float(row_data['anomaly_score']),
            "actual_class": int(row_data['Class']),
            "created_at": uploaded_at
        }
        detection_results_to_insert.append(detection_doc)

    detection_results_collection.insert_many(detection_results_to_insert)

    stats = detector.get_statistics(results_df)
    return {
        "message": "CSV processed successfully",
        "transactions_processed": len(results_df),
        "statistics": stats
    }


@router.post("/upload-csv", status_code=status.HTTP_201_CREATED)
async def upload_csv(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload CSV file and process transactions with fraud detection"""

    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed"
        )

    try:
        content = await file.read()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _process_upload_sync, content, current_user["id"])
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Error processing CSV: {str(e)}")


@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    """Get dashboard statistics for current user"""
    user_id = current_user["id"]

    pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id": None,
                "total_transactions": {"$sum": 1},
                "approved_transactions": {
                    "$sum": {"$cond": [{"$eq": ["$is_approved", True]}, 1, 0]}
                },
                "rejected_transactions": {
                    "$sum": {"$cond": [{"$eq": ["$is_approved", False]}, 1, 0]}
                },
                "fraud_detected": {
                    "$sum": {"$cond": [{"$eq": ["$is_fraud", True]}, 1, 0]}
                },
                "legitimate_transactions": {
                    "$sum": {"$cond": [{"$eq": ["$is_fraud", False]}, 1, 0]}
                }
            }
        }
    ]

    # Sync pymongo blocks the event loop — push it to the threadpool so
    # the dashboard's parallel requests can actually run in parallel.
    result = await run_in_threadpool(
        lambda: list(detection_results_collection.aggregate(pipeline))
    )

    if not result:
        return DashboardStats(
            total_transactions=0, approved_transactions=0, rejected_transactions=0,
            fraud_detected=0, legitimate_transactions=0,
            fraud_percentage=0.0, approval_rate=0.0
        )

    stats = result[0]
    total = stats['total_transactions']
    return DashboardStats(
        total_transactions=total,
        approved_transactions=stats['approved_transactions'],
        rejected_transactions=stats['rejected_transactions'],
        fraud_detected=stats['fraud_detected'],
        legitimate_transactions=stats['legitimate_transactions'],
        fraud_percentage=(stats['fraud_detected'] / total * 100) if total > 0 else 0.0,
        approval_rate=(stats['approved_transactions'] / total * 100) if total > 0 else 0.0
    )


# ── Anomaly Score Distribution ────────────────────────────────────────────────
# Previous approach loaded every detection_result for the user into Python and
# bucketed in numpy. For a Kaggle-sized upload (~284k rows) that meant pulling
# hundreds of MB across the Atlas network on every dashboard load.
#
# New approach does it entirely in Mongo:
#   1. One aggregation finds min/max anomaly_score + fraud/legit totals.
#   2. A second aggregation uses $facet + $bucket to bucket fraud and legit
#      counts into 20 fixed-width bins. Returns ~40 numbers total.

_HISTOGRAM_BIN_COUNT = 20


@router.get("/anomaly-score-distribution")
async def get_anomaly_score_distribution(current_user: dict = Depends(get_current_user)):
    """Histogram of anomaly_score for the current user, split by fraud/legit."""
    user_id = current_user["id"]

    # Pass 1: min/max + per-class totals in one aggregation.
    minmax_pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id": None,
                "min": {"$min": "$anomaly_score"},
                "max": {"$max": "$anomaly_score"},
                "fraud_total": {"$sum": {"$cond": [{"$eq": ["$is_fraud", True]}, 1, 0]}},
                "legit_total": {"$sum": {"$cond": [{"$eq": ["$is_fraud", False]}, 1, 0]}},
            }
        },
    ]
    mm = await run_in_threadpool(
        lambda: list(detection_results_collection.aggregate(minmax_pipeline))
    )

    if not mm:
        return {"bins": [], "fraud_counts": [], "legit_counts": []}

    mn = float(mm[0]["min"])
    mx = float(mm[0]["max"])
    fraud_total = int(mm[0]["fraud_total"])
    legit_total = int(mm[0]["legit_total"])

    # Edge case: every score is the same — return a single-bin histogram.
    if mn == mx:
        return {
            "bins": [f"{mn:.3f}"],
            "fraud_counts": [fraud_total],
            "legit_counts": [legit_total],
        }

    # Build 21 boundaries → 20 bins. Nudge the final boundary up slightly so
    # values exactly equal to mx land in the last bucket instead of "default".
    bin_edges = np.linspace(mn, mx, _HISTOGRAM_BIN_COUNT + 1).tolist()
    bin_edges[-1] = mx + max(abs(mx), 1.0) * 1e-9

    # Pass 2: bucket fraud and legit separately with $facet.
    bucket_pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$facet": {
                "fraud": [
                    {"$match": {"is_fraud": True}},
                    {
                        "$bucket": {
                            "groupBy": "$anomaly_score",
                            "boundaries": bin_edges,
                            "default": "outliers",
                            "output": {"count": {"$sum": 1}},
                        }
                    },
                ],
                "legit": [
                    {"$match": {"is_fraud": False}},
                    {
                        "$bucket": {
                            "groupBy": "$anomaly_score",
                            "boundaries": bin_edges,
                            "default": "outliers",
                            "output": {"count": {"$sum": 1}},
                        }
                    },
                ],
            }
        },
    ]
    facet_result = await run_in_threadpool(
        lambda: list(detection_results_collection.aggregate(bucket_pipeline))
    )

    fraud_buckets = facet_result[0]["fraud"] if facet_result else []
    legit_buckets = facet_result[0]["legit"] if facet_result else []

    # $bucket returns a sparse list of {_id: lower_boundary, count: N} — only
    # buckets with at least one document. Expand to a dense 20-element array.
    def _densify(buckets):
        counts = [0] * _HISTOGRAM_BIN_COUNT
        for b in buckets:
            if b["_id"] == "outliers":
                continue
            # _id is exactly one of the boundary floats we sent in. Match by
            # nearest-edge index using a small tolerance to be safe against
            # any float-roundtrip drift.
            lower = float(b["_id"])
            # bin_edges has 21 entries; the first 20 are lower boundaries.
            for i in range(_HISTOGRAM_BIN_COUNT):
                if abs(bin_edges[i] - lower) <= 1e-9 * max(abs(bin_edges[i]), 1.0):
                    counts[i] = int(b["count"])
                    break
        return counts

    return {
        "bins": [f"{bin_edges[i]:.3f}" for i in range(_HISTOGRAM_BIN_COUNT)],
        "fraud_counts": _densify(fraud_buckets),
        "legit_counts": _densify(legit_buckets),
    }


# ── Amount vs Anomaly Score Scatter ──────────────────────────────────────────
# Old approach: $lookup with $toObjectId inside $expr — bypasses _id index,
#               causes a full collection scan per sampled document.
# New approach: two-step join — sample detection_results (indexed), then fetch
#               transactions by _id using $in (uses the _id index).

@router.get("/amount-vs-anomaly")
async def get_amount_vs_anomaly(current_user: dict = Depends(get_current_user)):
    """Scatter: Amount (x) vs anomaly_score (y), coloured by fraud/legit."""
    user_id = current_user["id"]

    # Step 1 — sample detection results (user_id index used)
    sample_docs = await run_in_threadpool(
        lambda: list(detection_results_collection.aggregate([
            {"$match": {"user_id": user_id}},
            {"$sample": {"size": 2000}},
            {"$project": {"transaction_id": 1, "anomaly_score": 1, "is_fraud": 1, "_id": 0}}
        ]))
    )

    if not sample_docs:
        return {"fraud_points": [], "legit_points": []}

    # Step 2 — fetch transaction amounts by _id using $in (uses _id index)
    txn_ids = [ObjectId(d["transaction_id"]) for d in sample_docs if d.get("transaction_id")]
    txn_amount = await run_in_threadpool(
        lambda: {
            str(doc["_id"]): doc["Amount"]
            for doc in transactions_collection.find(
                {"_id": {"$in": txn_ids}},
                {"Amount": 1}
            )
        }
    )

    # Step 3 — merge in Python
    fraud_points, legit_points = [], []
    for doc in sample_docs:
        amount = txn_amount.get(doc.get("transaction_id"))
        if amount is None:
            continue
        point = {"x": amount, "y": doc["anomaly_score"]}
        (fraud_points if doc.get("is_fraud") else legit_points).append(point)

    return {"fraud_points": fraud_points, "legit_points": legit_points}


# ── Transactions Over Time ────────────────────────────────────────────────────

@router.get("/transactions-over-time")
async def get_transactions_over_time(current_user: dict = Depends(get_current_user)):
    """Daily upload counts and fraud counts for the current user."""
    user_id = current_user["id"]

    pipeline = [
        {"$match": {"user_id": user_id}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "total": {"$sum": 1},
                "fraud": {"$sum": {"$cond": [{"$eq": ["$is_fraud", True]}, 1, 0]}}
            }
        },
        {"$sort": {"_id": 1}}
    ]

    results = await run_in_threadpool(
        lambda: list(detection_results_collection.aggregate(pipeline))
    )
    return {
        "dates":        [r["_id"]   for r in results],
        "total_counts": [r["total"] for r in results],
        "fraud_counts": [r["fraud"] for r in results]
    }

from fastapi import APIRouter, Depends
from typing import List
from models import AdminStats, UserFraudRate
from database import users_collection, detection_results_collection
from auth import get_current_admin

router = APIRouter(prefix="/api/admin", tags=["Admin"])

@router.get("/analytics", response_model=AdminStats)
async def get_admin_analytics(current_admin: dict = Depends(get_current_admin)):
    """Get global analytics across all users (admin only)"""
    
    # Get total users (exclude password field)
    total_users = users_collection.count_documents({})
    
    # Aggregate all detection results
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
        # No transactions in system
        return AdminStats(
            total_users=total_users,
            total_transactions=0,
            total_fraud_detected=0,
            global_fraud_rate=0.0,
            global_approval_rate=0.0,
            approved_transactions=0,
            rejected_transactions=0
        )
    
    stats = result[0]
    total_transactions = stats['total_transactions']
    total_fraud = stats['total_fraud_detected']
    approved = stats['approved_transactions']
    
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
    
    # Aggregate fraud rates by user
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
                    {
                        "$match": {
                            "$expr": {
                                "$eq": [{"$toString": "$_id"}, "$$user_id_str"]
                            }
                        }
                    }
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
    
    fraud_rates = []
    for result in results:
        fraud_rates.append(UserFraudRate(
            user_id=result['user_id'],
            username=result['username'],
            email=result['email'],
            total_transactions=result['total_transactions'],
            fraud_count=result['fraud_count'],
            fraud_rate=result['fraud_rate']
        ))
    
    return fraud_rates

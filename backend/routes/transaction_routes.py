from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File
from typing import List
from datetime import datetime
from bson import ObjectId
from models import DashboardStats
from database import transactions_collection, detection_results_collection
from auth import get_current_user
from fraud_detection import detector

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])

@router.post("/upload-csv", status_code=status.HTTP_201_CREATED)
async def upload_csv(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload CSV file and process transactions with fraud detection"""
    
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are allowed"
        )
    
    try:
        # Read file content
        content = await file.read()
        
        # Process CSV with fraud detection
        original_df, results_df = detector.process_csv(content)
        
        # Store transactions and detection results
        user_id = current_user["id"]
        uploaded_at = datetime.utcnow()
        
        transactions_to_insert = []
        detection_results_to_insert = []
        
        for idx, row in results_df.iterrows():
            # Create transaction document
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
        
        # Create detection results
        for idx, (row, transaction_id) in enumerate(zip(results_df.iterrows(), transaction_ids)):
            _, row_data = row
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
        
        # Bulk insert detection results
        detection_results_collection.insert_many(detection_results_to_insert)
        
        # Get statistics
        stats = detector.get_statistics(results_df)
        
        return {
            "message": "CSV processed successfully",
            "transactions_processed": len(results_df),
            "statistics": stats
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing CSV: {str(e)}"
        )

@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    """Get dashboard statistics for current user"""
    user_id = current_user["id"]
    
    # Aggregate detection results for the user
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
    
    result = list(detection_results_collection.aggregate(pipeline))
    
    if not result:
        # No transactions yet
        return DashboardStats(
            total_transactions=0,
            approved_transactions=0,
            rejected_transactions=0,
            fraud_detected=0,
            legitimate_transactions=0,
            fraud_percentage=0.0,
            approval_rate=0.0
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

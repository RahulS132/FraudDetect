from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure
from config import get_settings
from datetime import datetime
import certifi

settings = get_settings()
client = None

# MongoDB client with certifi for SSL
try:
    client = MongoClient(
        settings.MONGODB_URL,
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        tlsCAFile=certifi.where()  # Use certifi for SSL certificates
    )
    # Test connection
    client.admin.command('ping')
    print("✓ MongoDB Atlas connected successfully!")
except ConnectionFailure as e:
    print(f"✗ MongoDB connection failed: {e}")
    print("Check: 1) Internet connection 2) MongoDB Atlas IP whitelist 3) Credentials")
except Exception as e:
    print(f"✗ Unexpected error: {e}")

if client is not None:
    db = client[settings.DATABASE_NAME]
    # Collections
    users_collection = db["users"]
    transactions_collection = db["transactions"]
    detection_results_collection = db["detection_results"]
else:
    db = None
    users_collection = None
    transactions_collection = None
    detection_results_collection = None

def init_db():
    """Initialize database with indexes"""
    if db is None:
        print("Index creation skipped: database connection is not available")
        return

    try:
        # ── users ──────────────────────────────────────────────────────────
        users_collection.create_index([("email", ASCENDING)], unique=True)
        users_collection.create_index([("username", ASCENDING)], unique=True)

        # ── transactions ───────────────────────────────────────────────────
        transactions_collection.create_index([("user_id", ASCENDING)])
        transactions_collection.create_index([("created_at", DESCENDING)])

        # ── detection_results ──────────────────────────────────────────────
        # Single-field indexes (original)
        detection_results_collection.create_index([("user_id", ASCENDING)])
        detection_results_collection.create_index([("transaction_id", ASCENDING)])
        detection_results_collection.create_index([("created_at", DESCENDING)])

        # Compound indexes for dashboard chart queries
        # Used by: anomaly-score-distribution, transactions-over-time (user scoped)
        detection_results_collection.create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)]
        )
        # Used by: v-feature-boxplots, amount-distribution (filter by is_fraud globally)
        detection_results_collection.create_index([("is_fraud", ASCENDING)])
        # Used by: user amount-vs-anomaly (filter user then sample)
        detection_results_collection.create_index(
            [("user_id", ASCENDING), ("is_fraud", ASCENDING)]
        )

        print("✓ Database indexes created")
    except Exception as e:
        print(f"Index creation warning: {e}")

def get_db():
    if db is None:
        raise RuntimeError("Database is not initialized. Check MONGODB_URL and MongoDB Atlas access settings.")
    return db

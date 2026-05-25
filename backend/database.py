from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure
from config import get_settings
from datetime import datetime
import certifi

settings = get_settings()

# MongoDB client with certifi for SSL.
# We deliberately raise on failure so the app fails fast at startup rather than
# handing out None collections that crash at request time.
try:
    client = MongoClient(
        settings.MONGODB_URL,
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        tlsCAFile=certifi.where(),  # Use certifi for SSL certificates
    )
    # Test connection
    client.admin.command("ping")
    print("✓ MongoDB Atlas connected successfully!")
except ConnectionFailure as e:
    raise RuntimeError(
        f"MongoDB connection failed: {e}\n"
        "Check: 1) Internet connection  2) MongoDB Atlas IP whitelist  "
        "3) Credentials in backend/.env (MONGODB_URL)"
    ) from e
except Exception as e:
    raise RuntimeError(
        f"Unexpected error initializing MongoDB client: {e}\n"
        "Check MONGODB_URL in backend/.env"
    ) from e

db = client[settings.DATABASE_NAME]
# Collections
users_collection = db["users"]
transactions_collection = db["transactions"]
detection_results_collection = db["detection_results"]


def init_db():
    """Initialize database with indexes"""
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
    return db

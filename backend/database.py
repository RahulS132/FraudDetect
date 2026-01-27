from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure
from config import get_settings
from datetime import datetime
import certifi

settings = get_settings()

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

db = client[settings.DATABASE_NAME]

# Collections
users_collection = db["users"]
transactions_collection = db["transactions"]
detection_results_collection = db["detection_results"]

def init_db():
    """Initialize database with indexes"""
    try:
        # Create indexes
        users_collection.create_index([("email", ASCENDING)], unique=True)
        users_collection.create_index([("username", ASCENDING)], unique=True)
        transactions_collection.create_index([("user_id", ASCENDING)])
        transactions_collection.create_index([("created_at", DESCENDING)])
        detection_results_collection.create_index([("user_id", ASCENDING)])
        detection_results_collection.create_index([("transaction_id", ASCENDING)])
        detection_results_collection.create_index([("created_at", DESCENDING)])
        
        print("✓ Database indexes created")
    except Exception as e:
        print(f"Index creation warning: {e}")

def get_db():
    return db
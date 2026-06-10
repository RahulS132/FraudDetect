from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
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
        tlsCAFile=certifi.where(),  # Use certifi for SSL certificates
        # ── Connection pool ──────────────────────────────────────────────────
        # Atlas free tier (M0) allows up to 500 connections. We keep a small,
        # bounded pool well under that limit so the app never exhausts Atlas —
        # even with reloads, multiple workers, or many concurrent requests.
        maxPoolSize=20,            # cap concurrent sockets
        minPoolSize=0,             # don't hold idle sockets open on M0
        maxIdleTimeMS=30000,       # reap idle sockets after 30s
        waitQueueTimeoutMS=10000,  # fail fast instead of hanging if pool is busy
        # ── Timeouts ─────────────────────────────────────────────────────────
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
        socketTimeoutMS=45000,     # kill a query that hangs (prevents stuck threads)
        # ── Reliability ──────────────────────────────────────────────────────
        retryWrites=True,          # retry a write once on transient network blips
        retryReads=True,
        appname="frauddetect",     # shows up in Atlas metrics for debugging
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
notifications_collection = db["notifications"]
audit_logs_collection = db["audit_logs"]

# ── Second expansion collections ─────────────────────────────────────────────
transaction_rules_collection = db["transaction_rules"]   # admin blocking rules
fraud_config_collection = db["fraud_config"]             # single settings doc
fraud_events_collection = db["fraud_events"]             # auto-block/flag events
account_events_collection = db["account_events"]         # balance/credit history
user_status_events_collection = db["user_status_events"] # block/unblock history
# Phase 2 (created here so indexes exist ahead of time)
email_verifications_collection = db["email_verifications"]
login_attempts_collection = db["login_attempts"]


def init_db():
    """Initialize database with indexes (idempotent)."""
    try:
        # ── users ──────────────────────────────────────────────────────────
        users_collection.create_index([("email", ASCENDING)], unique=True)
        users_collection.create_index([("username", ASCENDING)], unique=True)

        # ── transactions ───────────────────────────────────────────────────
        transactions_collection.create_index([("user_id", ASCENDING)])
        transactions_collection.create_index([("created_at", DESCENDING)])
        # New business fields for the manual/CRUD + search features
        transactions_collection.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
        transactions_collection.create_index([("category", ASCENDING)])
        transactions_collection.create_index([("tags", ASCENDING)])
        transactions_collection.create_index([("source", ASCENDING)])
        transactions_collection.create_index([("Amount", ASCENDING)])
        transactions_collection.create_index([("tag", ASCENDING)])
        transactions_collection.create_index([("creation_source", ASCENDING)])
        # Denormalized fraud fields (mirrored from detection_results) so the
        # search/listing query can filter + sort on this collection alone.
        transactions_collection.create_index([("is_fraud", ASCENDING)])
        transactions_collection.create_index([("anomaly_score", ASCENDING)])
        # Compound indexes matching the search's default sort orders.
        transactions_collection.create_index(
            [("user_id", ASCENDING), ("is_fraud", ASCENDING), ("created_at", DESCENDING)]
        )
        transactions_collection.create_index([("Amount", DESCENDING)])
        # Full-text search across description + category + tags. A collection can
        # only have ONE text index, so we combine the searchable string fields.
        try:
            transactions_collection.create_index(
                [("description", TEXT), ("category", TEXT), ("tags", TEXT)],
                name="txn_text_search",
                default_language="english",
            )
        except Exception as e:
            # A text index with different fields may already exist — that's fine.
            print(f"Text index note: {e}")

        # ── detection_results ──────────────────────────────────────────────
        detection_results_collection.create_index([("user_id", ASCENDING)])
        detection_results_collection.create_index([("transaction_id", ASCENDING)])
        detection_results_collection.create_index([("created_at", DESCENDING)])
        detection_results_collection.create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)]
        )
        detection_results_collection.create_index([("is_fraud", ASCENDING)])
        detection_results_collection.create_index(
            [("user_id", ASCENDING), ("is_fraud", ASCENDING)]
        )
        detection_results_collection.create_index([("severity", ASCENDING)])

        # ── notifications ──────────────────────────────────────────────────
        notifications_collection.create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)]
        )
        notifications_collection.create_index(
            [("audience", ASCENDING), ("created_at", DESCENDING)]
        )
        notifications_collection.create_index([("is_read", ASCENDING)])

        # ── audit_logs ─────────────────────────────────────────────────────
        audit_logs_collection.create_index([("created_at", DESCENDING)])
        audit_logs_collection.create_index([("actor_id", ASCENDING)])
        audit_logs_collection.create_index([("target_user_id", ASCENDING)])
        audit_logs_collection.create_index([("action", ASCENDING)])

        # ── second expansion ───────────────────────────────────────────────
        # users: status filtering for admin user management
        users_collection.create_index([("status", ASCENDING)])
        # transaction rules
        transaction_rules_collection.create_index([("enabled", ASCENDING)])
        transaction_rules_collection.create_index([("rule_type", ASCENDING)])
        transaction_rules_collection.create_index([("created_at", DESCENDING)])
        # fraud events
        fraud_events_collection.create_index([("created_at", DESCENDING)])
        fraud_events_collection.create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)]
        )
        # account events (balance + credit-limit history)
        account_events_collection.create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)]
        )
        account_events_collection.create_index([("type", ASCENDING)])
        # user status events (block/unblock history)
        user_status_events_collection.create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)]
        )
        # Phase 2 collections
        email_verifications_collection.create_index([("email", ASCENDING)])
        email_verifications_collection.create_index(
            [("expires_at", ASCENDING)], expireAfterSeconds=0
        )
        login_attempts_collection.create_index(
            [("user_id", ASCENDING), ("created_at", DESCENDING)]
        )
        login_attempts_collection.create_index([("email", ASCENDING)])

        print("✓ Database indexes created")
    except Exception as e:
        print(f"Index creation warning: {e}")

    # NOTE: the one-time denormalization backfill is intentionally NOT run on
    # startup — on a large collection it would block boot. Run it once manually:
    #     python backfill.py
    # New uploads/admin-created transactions already write the denormalized
    # fields, and the search service falls back to the joined detection_result
    # for any rows not yet backfilled, so the app works correctly either way.


def get_db():
    return db

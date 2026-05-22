# FraudDetect Database Schema

MongoDB collections and document structure for the FraudDetect application.

## Database Name
`frauddetect`

## Collections

### 1. users

Stores user account information.

**Indexes:**
- `email` (unique)
- `username` (unique)

**Document Structure:**
```json
{
  "_id": ObjectId("..."),
  "email": "user@example.com",
  "username": "johndoe",
  "full_name": "John Doe",
  "hashed_password": "$2b$12$...",
  "role": "user",  // "user" or "admin"
  "created_at": ISODate("2024-01-01T00:00:00Z")
}
```

**Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | ObjectId | Yes | MongoDB document ID |
| `email` | String | Yes | User email (unique) |
| `username` | String | Yes | Username (unique, alphanumeric) |
| `full_name` | String | No | User's full name |
| `hashed_password` | String | Yes | Bcrypt hashed password |
| `role` | String | Yes | User role: "user" or "admin" |
| `created_at` | DateTime | Yes | Account creation timestamp |

**Sample Document:**
```json
{
  "_id": ObjectId("65a1b2c3d4e5f6g7h8i9j0k1"),
  "email": "john.doe@example.com",
  "username": "johndoe",
  "full_name": "John Doe",
  "hashed_password": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYIbXQw.Nni",
  "role": "user",
  "created_at": ISODate("2024-01-15T10:30:00Z")
}
```

**Constraints:**
- Email must be valid email format
- Username must be 3+ characters, alphanumeric only
- Password must be 6+ characters (stored hashed)
- Role must be "user" or "admin"

---

### 2. transactions

Stores raw transaction data uploaded by users.

**Indexes:**
- `user_id` (ascending)
- `created_at` (descending)

**Document Structure:**
```json
{
  "_id": ObjectId("..."),
  "user_id": "65a1b2c3d4e5f6g7h8i9j0k1",
  "Time": 0.0,
  "V1": -1.359807,
  "V2": -0.072781,
  "V3": 2.536347,
  "V4": 1.378155,
  "V5": -0.338321,
  "V6": 0.462388,
  "V7": 0.239599,
  "V8": 0.098698,
  "V9": 0.363787,
  "V10": 0.090794,
  "V11": -0.551600,
  "V12": -0.617801,
  "V13": -0.991390,
  "V14": -0.311169,
  "V15": 1.468177,
  "V16": -0.470401,
  "V17": 0.207971,
  "V18": 0.025791,
  "V19": 0.403993,
  "V20": 0.251412,
  "V21": -0.018307,
  "V22": 0.277838,
  "V23": -0.110474,
  "V24": 0.066928,
  "V25": 0.128539,
  "V26": -0.189115,
  "V27": 0.133558,
  "V28": -0.021053,
  "Amount": 149.62,
  "Class": 0,
  "created_at": ISODate("2024-01-15T11:00:00Z")
}
```

**Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | ObjectId | Yes | MongoDB document ID |
| `user_id` | String | Yes | Reference to user who uploaded |
| `Time` | Float | Yes | Transaction time in seconds |
| `V1-V28` | Float | Yes | PCA transformed features |
| `Amount` | Float | Yes | Transaction amount |
| `Class` | Integer | Yes | 0=Legitimate, 1=Fraud |
| `created_at` | DateTime | Yes | Upload timestamp |

**Notes:**
- V1-V28 are principal components from PCA transformation
- Original features are confidential (Kaggle dataset)
- Each transaction belongs to one user
- Transactions are immutable once uploaded

---

### 3. detection_results

Stores fraud detection results for each transaction.

**Indexes:**
- `user_id` (ascending)
- `transaction_id` (ascending)
- `created_at` (descending)

**Document Structure:**
```json
{
  "_id": ObjectId("..."),
  "transaction_id": "65a1b2c3d4e5f6g7h8i9j0k2",
  "user_id": "65a1b2c3d4e5f6g7h8i9j0k1",
  "is_fraud": false,
  "is_approved": true,
  "anomaly_score": -0.123456,
  "actual_class": 0,
  "created_at": ISODate("2024-01-15T11:00:00Z")
}
```

**Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `_id` | ObjectId | Yes | MongoDB document ID |
| `transaction_id` | String | Yes | Reference to transaction |
| `user_id` | String | Yes | Reference to user |
| `is_fraud` | Boolean | Yes | True if fraud detected |
| `is_approved` | Boolean | Yes | True if transaction approved |
| `anomaly_score` | Float | Yes | Isolation Forest anomaly score |
| `actual_class` | Integer | Yes | Original class from CSV (0 or 1) |
| `created_at` | DateTime | Yes | Detection timestamp |

**Detection Logic:**
- `is_fraud = True` if:
  - Isolation Forest detects anomaly (score < threshold) OR
  - `actual_class = 1` (labeled as fraud in CSV)
- `is_approved = !is_fraud`
- Lower anomaly scores indicate higher fraud probability

**Sample Documents:**

Legitimate Transaction:
```json
{
  "_id": ObjectId("65a1b2c3d4e5f6g7h8i9j0k3"),
  "transaction_id": "65a1b2c3d4e5f6g7h8i9j0k2",
  "user_id": "65a1b2c3d4e5f6g7h8i9j0k1",
  "is_fraud": false,
  "is_approved": true,
  "anomaly_score": -0.089234,
  "actual_class": 0,
  "created_at": ISODate("2024-01-15T11:00:00Z")
}
```

Fraudulent Transaction:
```json
{
  "_id": ObjectId("65a1b2c3d4e5f6g7h8i9j0k4"),
  "transaction_id": "65a1b2c3d4e5f6g7h8i9j0k5",
  "user_id": "65a1b2c3d4e5f6g7h8i9j0k1",
  "is_fraud": true,
  "is_approved": false,
  "anomaly_score": -0.456789,
  "actual_class": 1,
  "created_at": ISODate("2024-01-15T11:00:01Z")
}
```

---

## Relationships

```
users (1) ----< (many) transactions
  |
  |
  └----< (many) detection_results

transactions (1) ----< (1) detection_results
```

- One user can have many transactions
- One user can have many detection results
- Each transaction has exactly one detection result
- Relationships maintained via `user_id` and `transaction_id` fields

---

## Aggregation Queries

### User Dashboard Statistics

```javascript
db.detection_results.aggregate([
  { $match: { user_id: "user_id_here" } },
  {
    $group: {
      _id: null,
      total_transactions: { $sum: 1 },
      approved_transactions: {
        $sum: { $cond: [{ $eq: ["$is_approved", true] }, 1, 0] }
      },
      rejected_transactions: {
        $sum: { $cond: [{ $eq: ["$is_approved", false] }, 1, 0] }
      },
      fraud_detected: {
        $sum: { $cond: [{ $eq: ["$is_fraud", true] }, 1, 0] }
      },
      legitimate_transactions: {
        $sum: { $cond: [{ $eq: ["$is_fraud", false] }, 1, 0] }
      }
    }
  }
]);
```

### Admin Global Statistics

```javascript
db.detection_results.aggregate([
  {
    $group: {
      _id: null,
      total_transactions: { $sum: 1 },
      total_fraud_detected: {
        $sum: { $cond: [{ $eq: ["$is_fraud", true] }, 1, 0] }
      },
      approved_transactions: {
        $sum: { $cond: [{ $eq: ["$is_approved", true] }, 1, 0] }
      },
      rejected_transactions: {
        $sum: { $cond: [{ $eq: ["$is_approved", false] }, 1, 0] }
      }
    }
  }
]);
```

### Fraud Rate by User

```javascript
db.detection_results.aggregate([
  {
    $group: {
      _id: "$user_id",
      total_transactions: { $sum: 1 },
      fraud_count: {
        $sum: { $cond: [{ $eq: ["$is_fraud", true] }, 1, 0] }
      }
    }
  },
  {
    $lookup: {
      from: "users",
      let: { user_id_str: "$_id" },
      pipeline: [
        {
          $match: {
            $expr: { $eq: [{ $toString: "$_id" }, "$$user_id_str"] }
          }
        }
      ],
      as: "user_info"
    }
  },
  { $unwind: "$user_info" },
  {
    $project: {
      user_id: "$_id",
      username: "$user_info.username",
      email: "$user_info.email",
      total_transactions: 1,
      fraud_count: 1,
      fraud_rate: {
        $multiply: [{ $divide: ["$fraud_count", "$total_transactions"] }, 100]
      }
    }
  },
  { $sort: { fraud_rate: -1 } }
]);
```

---

## Data Retention

**Recommendations:**
- Keep transactions indefinitely for audit trail
- Archive old detection results after 1 year
- Backup database weekly
- Implement data export for users (GDPR compliance)

---

## Data Privacy

**User Data Protection:**
- Passwords are hashed with bcrypt (never stored in plain text)
- Users can only access their own transactions
- Admins cannot see user passwords
- Transaction data isolated by user_id
- MongoDB Atlas encryption at rest

**Admin Access:**
- Admins see aggregated statistics only
- Admins see usernames and emails (not passwords)
- Admins see fraud rates by user
- No access to individual transaction details of other users

---

## Performance Considerations

**Indexes:**
- All recommended indexes are created automatically on startup
- Compound indexes for common queries
- Index on foreign key fields (user_id, transaction_id)

**Query Optimization:**
- Use aggregation pipelines for statistics
- Limit result sets with pagination
- Project only needed fields

**Scaling:**
- MongoDB sharding on user_id for horizontal scaling
- Read replicas for reporting queries
- Connection pooling (default with pymongo)

---

## Backup Strategy

**Recommended Approach:**
1. Enable MongoDB Atlas automated backups
2. Export collections weekly to JSON
3. Store exports in secure cloud storage
4. Test restore procedures monthly

**Backup Command:**
```bash
mongodump --uri="mongodb+srv://..." --db=frauddetect --out=./backup
```

**Restore Command:**
```bash
mongorestore --uri="mongodb+srv://..." --db=frauddetect ./backup/frauddetect
```

---

## Migration Notes

**Initial Setup:**
```python
from database import init_db
init_db()  # Creates all indexes
```

**Adding Admin User:**
```python
from auth import get_password_hash
from database import users_collection
from datetime import datetime

admin_user = {
    "email": "admin@frauddetect.com",
    "username": "admin",
    "full_name": "System Administrator",
    "hashed_password": get_password_hash("secure_password"),
    "role": "admin",
    "created_at": datetime.utcnow()
}
users_collection.insert_one(admin_user)
```

---

**Schema Version:** 1.0  
**Last Updated:** 2024-01-15

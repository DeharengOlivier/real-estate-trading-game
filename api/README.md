# API Backend

FastAPI backend for the real estate trading game.

## Main Files

### main.py
Application entry point.

**Responsibilities:**
- Creating the FastAPI app
- CORS configuration
- Registering the routers
- Lifecycle management (startup/shutdown)
- Connecting to the databases at startup

**Mounted routers:**
- `/auth` - Authentication
- `/portfolio` - User portfolio
- `/trading` - Buy/sell
- `/game` - Game mechanics
- `/charts` - Chart data
- `/admin` - Administration
- `/health` - Health check

### database.py
Database connection management.

**MongoDB:**
- Client: AsyncIOMotorClient
- Database: `realestate`
- Collections: users, portfolios, properties, listings, holdings, trades, marketindex, pricehistory, renovations
- Function: `get_database()` returns the instance

**Redis:**
- Client: aioredis
- Usage: rate limiting on registration
- Function: `get_redis_client()` returns the instance or None
- Fallback: in-memory dictionary if Redis is unavailable

**Lifecycle:**
- `connect_to_mongo()` - Called at startup
- `connect_to_redis()` - Called at startup
- `close_mongo_connection()` - Called at shutdown
- `close_redis_connection()` - Called at shutdown

### models.py
Pydantic schemas for request validation.

**User Models:**
- `UserCreate` - Registration (username, email, password, name)
- `UserLogin` - Login (username, password)
- `Token` - JWT response (access_token, token_type)

**Trading Models:**
- `BuyRequest` - Buy (propertyId)
- `SellRequest` - Sell (holdingId)

**Property Models:**
- `PropertyCreate` - Property creation (zone, type, surface, characteristics)
- `PropertyUpdate` - Property update

**Renovation Models:**
- `RenovationCreate` - New renovation type
- `RenovationApply` - Renovation application (holdingId, renovationCode)

**Automatic validation:**
- Python types (str, float, int, bool)
- Constraints (ge, le, min_length, max_length)
- Email validation
- Enums for fixed values

### services.py
Shared business logic.

**Main functions:**

`get_current_quarter(db)` - Returns the current quarter of the game
- Looks up the latest market index
- Format: "2024-Q2"

`get_property_current_price(db, property, current_quarter)` - Computes a property's price
- Formula: base_ppm * surface * trend * quality_multiplier
- quality_multiplier = 0.85 + (epc * 0.05) + (state * 0.05) + (kitchen * 0.03) + (bath * 0.02)
- trend: market index of the zone at the given quarter

`compute_property_price(property, market_index)` - Alternative version of the computation
- Same formula but with market_index passed directly

**Constants:**

`ZONE_TRENDS` - Growth trends by zone
- Dict with 12 Belgian zones
- Values between -0.02 and 0.04 (annual growth)

`BELGIUM_ZONES` - List of the 12 zones
- Bruxelles-Centre, Bruxelles-Sud, Anvers, Gand, etc.

`BASE_PPM` - Base price per m2
- house: 3500-4500 depending on the zone
- apartment: 3000-4200 depending on the zone

### auth.py
Authentication and authorization.

**JWT Configuration:**
- SECRET_KEY: environment variable
- ALGORITHM: HS256
- ACCESS_TOKEN_EXPIRE: 30 days

**Functions:**

`verify_password(plain, hashed)` - bcrypt verification

`get_password_hash(password)` - bcrypt hash

`create_access_token(data)` - JWT generation
- Payload: username, sub (user_id)
- Automatic expiration

`get_current_user(token)` - FastAPI dependency
- Decodes the JWT
- Checks validity
- Returns the user document
- Raises 401 if invalid

**Rate Limiting:**
- 5 attempts max per 5 minutes
- Redis key: `login_attempts:{username}`
- Sorted Set with timestamps
- Auto-expiration after 5 minutes
- In-memory fallback if Redis is down

## Database

### MongoDB Collections

**users**
```python
{
  "_id": ObjectId,
  "username": str,
  "email": str,
  "name": str,
  "hashedPassword": str,
  "roles": list[str],
  "createdAt": datetime
}
```
The balance is not here: it lives in `portfolios.cash`, which is what trading
moves. A copy on the user would be stale from the first purchase onwards.

**portfolios**
```python
{
  "_id": ObjectId,
  "userId": ObjectId,
  "cash": float,
  "createdAt": datetime,
  "updatedAt": datetime
}
```

**properties**
```python
{
  "_id": ObjectId,
  "zone": str,
  "type": "house" | "apartment",
  "surface": float,
  "base_ppm": float,
  "epc": float (0-1),
  "state": float (0-1),
  "kitchen": float (0-1),
  "bath": float (0-1)
}
```

**listings**
```python
{
  "_id": ObjectId,
  "propertyId": ObjectId,
  "isAvailable": bool,
  "lastComputedPrice": float,
  "listedAt": datetime
}
```

**holdings**
```python
{
  "_id": ObjectId,
  "userId": ObjectId,
  "propertyId": ObjectId,
  "purchasePrice": float,
  "purchaseDate": str,
  "purchaseFees": float,
  "totalRenovationCost": float,
  "renovationHistory": [str]
}
```

**trades**
```python
{
  "_id": ObjectId,
  "userId": ObjectId,
  "propertyId": ObjectId,
  "type": "buy" | "sell",
  "price": float,
  "fees": float,
  "timestamp": str,
  "createdAt": datetime
}
```

**marketindex**
```python
{
  "_id": ObjectId,
  "zone": str,
  "t": str (quarter),
  "trend": float
}
```

**pricehistory**
```python
{
  "_id": ObjectId,
  "propertyId": ObjectId,
  "t": str (quarter),
  "price": float
}
```

**renovations**
```python
{
  "_id": ObjectId,
  "code": str,
  "name": str,
  "description": str,
  "cost": float,
  "impactEpc": float,
  "impactState": float,
  "impactKitchen": float,
  "impactBath": float
}
```

## Dependencies

Listed in `requirements.txt`:
- fastapi - Web framework
- uvicorn - ASGI server
- motor - Async MongoDB driver
- pymongo - Sync MongoDB (for seed)
- redis - Async Redis client
- python-jose - JWT tokens
- passlib - bcrypt hashing
- pydantic - Validation
- python-multipart - File upload
- bcrypt - Password hashing

## Environment Variables

Defined in `docker-compose.yml`:
- `MONGODB_URL` - mongodb://mongo:27017
- `MONGODB_DB` - realestate
- `REDIS_URL` - redis://redis:6379
- `SECRET_KEY` - Key for JWT (generate in production)

## Running in Development

```bash
# With Docker (recommended)
docker-compose up -d

# Without Docker (local)
pip install -r requirements.txt
export MONGODB_URL=mongodb://localhost:27017
export REDIS_URL=redis://localhost:6379
export SECRET_KEY=your-secret-key
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

## Tests

See `api/tests/README.md`

## Logs

Configured in each module:
```python
import logging
logger = logging.getLogger(__name__)
logger.info("Message")
logger.error("Erreur", exc_info=True)
```

Default console format via uvicorn.

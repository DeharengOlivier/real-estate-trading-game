# API Routers

Organization of endpoints by functional domain.

## Structure

```
routers/
├── auth.py         Authentication and user management
├── portfolio.py    Asset overview
├── trading.py      Buying and selling properties
├── game.py         Game mechanics (next trim)
├── charts.py       Data for charts
├── admin.py        Data administration
└── health.py       Health check and status
```

## auth.py

**Endpoints:**
- `POST /auth/register` - Create an account
- `POST /auth/login` - Log in
- `GET /auth/me` - Logged-in user info

**Features:**
- Password hashing with bcrypt
- JWT token generation
- Rate limiting (5 attempts max per 5 minutes)
- Validation of unique email and username
- Automatic creation of the initial portfolio (1,000,000 cash)

**Security:**
- In-memory fallback if Redis is unavailable
- Tokens expire after 30 days
- No storage of the password in plain text

## portfolio.py

**Endpoints:**
- `GET /portfolio/summary` - Overview (cash + holdings)
- `GET /portfolio/performance` - Global P&L calculation

**Returned data:**
- Cash balance
- List of owned properties
- Current value of each asset
- Purchase price vs current price
- Realized and unrealized profit/loss
- Total asset value

**Logic:**
- Current price based on market indices
- P&L = (current price - purchase price - fees - renovations)
- Aggregation of all holdings by userId

## trading.py

**Endpoints:**
- `GET /trading/listings` - Available properties with filters
- `POST /trading/buy` - Buy a property
- `POST /trading/sell` - Sell a property

**Available filters:**
- Zone (12 Belgian zones)
- Type (house/apartment)
- Min/max price
- Sort (price, surface, zone)
- Pagination

**Buy transaction:**
1. Check property availability
2. Calculate current price + fees (2.5%)
3. Check sufficient balance
4. Deduct from cash
5. Create holding
6. Mark listing as unavailable
7. Record in trades

**Sell transaction:**
1. Check ownership of the property
2. Calculate current price - commission (2.5%)
3. Add to cash
4. Remove holding
5. Mark listing as available
6. Record in trades

**MongoDB Aggregation Pipeline:**
- Join listings + properties
- Multiple filters
- Sorting and pagination
- pricePerM2 calculation
- Enrichment with zone trends

## game.py

**Endpoints:**
- `GET /game/quarter` - Current game quarter
- `POST /game/advance` - Move to the next quarter
- `POST /game/renovate` - Apply a renovation

**Game mechanics:**
- Progression by quarters (2024-Q1 to 2028-Q4)
- Manual advancement by the user
- Update of market indices
- Recalculation of all prices

**Renovations:**
- Fixed catalog (insulation, kitchen, bathroom, etc.)
- Cost deducted from cash
- Modification of the property's characteristics
- Immediate impact on value

## charts.py

**Endpoints:**
- `GET /charts/market-index` - Indices by zone and quarter
- `GET /charts/price-history/{propertyId}` - History of a property

**Data:**
- Evolution of market indices (trend)
- Historical property prices
- Filters by zone and period
- Format suited for frontend charts

## admin.py

**Endpoints:**
- `POST /admin/properties` - Create a property
- `GET /admin/properties` - List all properties
- `GET /admin/properties/{id}` - Details of a property
- `PUT /admin/properties/{id}` - Update a property
- `DELETE /admin/properties/{id}` - Delete a property
- `POST /admin/renovations` - Create a renovation type
- `GET /admin/renovations` - List renovations
- `PUT /admin/renovations/{code}` - Update a renovation
- `DELETE /admin/renovations/{code}` - Delete a renovation
- `GET /admin/trades` - History of all transactions

**Access:**
- All authenticated users can use these endpoints
- No roles system

**Validation:**
- Pydantic schemas for each request
- Validation of data before insertion
- Handling of MongoDB ObjectId

## health.py

**Endpoints:**
- `GET /health` - Status of the API and dependencies

**Return:**
```json
{
  "status": "healthy",
  "timestamp": "2025-11-06T18:00:00.000000",
  "dependencies": {
    "mongodb": "connected",
    "redis": "connected"
  }
}
```

**Usage:**
- Docker health checks
- Production monitoring
- Connection debugging

## Common Dependencies

All routers use:
- `get_database()` - MongoDB instance
- `get_redis_client()` - Redis instance (optional)
- `get_current_user()` - JWT verification
- `get_current_quarter()` - Current game quarter
- `get_property_current_price()` - Price calculation

## Error Handling

HTTP codes used:
- `200` - Success
- `201` - Created
- `400` - Bad request
- `401` - Not authenticated
- `404` - Resource not found
- `409` - Conflict (duplicate)
- `429` - Too many requests
- `500` - Server error

## Applied Patterns

- Single Responsibility: one router = one domain
- Dependency Injection: FastAPI Depends()
- MongoDB transaction for atomic operations
- Graceful fallback if dependencies are unavailable
- Automatic validation with Pydantic

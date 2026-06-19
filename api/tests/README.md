# API Tests

Unit and integration tests for the FastAPI API.

## Structure

```
tests/
├── __init__.py        Package marker
├── conftest.py        Shared fixtures + in-memory MongoDB/Redis wiring
├── test_api.py        Health, buy/sell, listings filter
├── test_auth.py       Registration, login, JWT guards, rate limiting
├── test_admin.py      Property/renovation CRUD + auth guards
├── test_trading.py    Listings filters/pagination, buy, sell, P&L
├── test_portfolio.py  Summary, equity, unrealized P&L, holdings detail
├── test_game.py       Renovations, advance-quarter, current quarter
├── test_charts.py     Portfolio equity series, property price history
└── test_services.py   Pure unit tests (pricing, quarter math, auth helpers)
```

## conftest.py

The suite runs with NO external services. `conftest.py`:

- Monkeypatches `api.database.connect_to_mongo` / `connect_to_redis` so the app
  uses an in-memory `mongomock-motor` client and a `fakeredis` instance.
- Resets all collections and the rate-limit state before each test, then seeds a
  deterministic baseline (a `2020-1` market index for every zone and the full
  renovation catalog).

**Fixtures:**

`setup_database` (autouse) - resets and seeds the in-memory DB/Redis per test.

`test_user_and_token` - inserts a user (with `user` + `admin` roles) and its
portfolio, returning `(user_data, token, headers)` with a ready-to-use JWT.

## test_api.py

Tests for the main endpoints.

### Health Check Tests

`test_health_check()` - Check that the API responds
- GET /health
- Expect: 200 OK
- Expect: {"status": "healthy"}

### Authentication Tests

`test_register_success()` - Successful registration
- POST /auth/register with valid data
- Expect: 200 OK
- Expect: access_token returned
- Verify: user created in DB
- Verify: portfolio created with 1,000,000 cash

`test_register_duplicate()` - Prevent duplicates
- POST /auth/register with an existing username
- Expect: 409 Conflict

`test_login_success()` - Successful login
- POST /auth/login with valid credentials
- Expect: 200 OK
- Expect: access_token returned

`test_login_wrong_password()` - Reject wrong password
- POST /auth/login with wrong password
- Expect: 401 Unauthorized

`test_get_me()` - Retrieve user information
- GET /auth/me with JWT token
- Expect: 200 OK
- Expect: username, email, name

### Portfolio Tests

`test_portfolio_summary()` - Portfolio overview
- GET /portfolio/summary with auth
- Expect: 200 OK
- Expect: cash balance
- Expect: holdings array (empty at first)

`test_portfolio_unauthorized()` - Block access without auth
- GET /portfolio/summary without token
- Expect: 401 Unauthorized

### Trading Tests

`test_get_listings()` - List available properties
- GET /trading/listings
- Expect: 200 OK
- Expect: items array
- Expect: total, page, limit

`test_get_listings_filters()` - Filters work
- GET /trading/listings?zone=Bruxelles&type=house
- Expect: 200 OK
- Expect: filtered results

`test_buy_property()` - Buy a property
- POST /trading/buy with propertyId
- Expect: 200 OK
- Verify: cash deducted
- Verify: holding created
- Verify: trade recorded
- Verify: listing unavailable

`test_buy_insufficient_funds()` - Reject if not enough cash
- POST /trading/buy with price > cash
- Expect: 400 Bad Request

`test_sell_property()` - Sell a property
- POST /trading/sell with holdingId
- Expect: 200 OK
- Verify: cash added
- Verify: holding removed
- Verify: trade recorded
- Verify: listing available

### Game Tests

`test_get_quarter()` - Retrieve the current quarter
- GET /game/quarter
- Expect: 200 OK
- Expect: format "YYYY-QN"

`test_advance_quarter()` - Advance to the next quarter
- POST /game/advance
- Expect: 200 OK
- Verify: indices updated

### Admin Tests

`test_create_property()` - Create a property (admin)
- POST /admin/properties with data
- Expect: 201 Created
- Verify: property in DB
- Verify: listing created

`test_delete_property()` - Delete a property
- DELETE /admin/properties/{id}
- Expect: 200 OK
- Verify: property deleted
- Verify: listing deleted

`test_list_trades()` - Transaction history
- GET /admin/trades
- Expect: 200 OK
- Expect: array of trades

## Running the Tests

### All tests
```bash
docker exec realestate-api pytest api/tests/ -v
```

### A specific test
```bash
docker exec realestate-api pytest api/tests/test_api.py::test_buy_property -v
```

### With coverage
```bash
docker exec realestate-api pytest api/tests/ --cov=api --cov-report=term-missing
```

### Verbose mode with logs
```bash
docker exec realestate-api pytest api/tests/ -v -s
```

## Assertions Used

**Status codes:**
```python
assert response.status_code == 200
assert response.status_code == 201
assert response.status_code == 400
assert response.status_code == 401
assert response.status_code == 404
assert response.status_code == 409
```

**JSON content:**
```python
assert "access_token" in response.json()
assert response.json()["cash"] == 1000000
assert len(response.json()["items"]) > 0
```

**Database:**
```python
user = await db.users.find_one({"username": "testuser"})
assert user is not None
assert user["email"] == "test@example.com"
```

## Mocking

No real services are needed:

- **MongoDB** -> `mongomock-motor`, an in-memory async client that is a drop-in
  for `motor`. Aggregation pipelines (`$lookup`, `$unwind`, `$facet`) used by the
  listings endpoint run against it.
- **Redis** -> `fakeredis` (async), so rate limiting is actually exercised in
  tests (both the Redis path and the in-memory fallback path) rather than
  disabled.

Both are installed via `api/requirements-dev.txt`.

## Current Coverage

76 tests, all passing.

**Covered areas:**
- Authentication (register, login, JWT, rate limiting)
- Portfolio summary, equity and P&L
- Trading buy/sell incl. insufficient funds and ongoing-renovation guard
- Game mechanics incl. renovations and advancing quarters
- Admin CRUD for properties and renovations
- Charts (equity series, price history)
- Pricing/quarter/renovation unit tests

## Adding New Tests

Template:
```python
def test_descriptive_name(client, test_db, test_user):
    """Describe the behavior being tested"""
    # Arrange
    data = {"key": "value"}
    headers = {"Authorization": f"Bearer {test_user['token']}"}
    
    # Act
    response = client.post("/endpoint", json=data, headers=headers)
    
    # Assert
    assert response.status_code == 200
    assert response.json()["expected_key"] == "expected_value"
```

## Debugging Tests

Show the logs:
```bash
pytest api/tests/ -v -s --log-cli-level=DEBUG
```

Stop at the first failure:
```bash
pytest api/tests/ -x
```

Interactive mode (PDB):
```python
def test_example():
    import pdb; pdb.set_trace()
    # ...
```

## Best Practices

- One test = one feature
- Descriptive names (test_action_expected_result)
- Arrange-Act-Assert pattern
- Automatic cleanup via fixtures
- Isolation between tests
- No dependencies between tests
- Mock external services
